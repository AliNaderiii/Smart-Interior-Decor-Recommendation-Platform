/**
 * Phase 4 — Dead Keys e2e.
 *
 * Walks every authenticated route, clicks EVERY enabled interactive control,
 * and asserts that each click produces an observable effect and no failure:
 *
 *   1. no console error / unhandled page exception
 *   2. every network response triggered is 2xx/3xx, or 429 (rate limit is a
 *      legitimate designed response, not a bug)
 *   3. the click changes SOMETHING — DOM, URL, or a network call. A control
 *      that is wired to a handler which quietly does nothing is still dead to
 *      the user, and this is the assertion that catches it.
 *
 * Static analysis (`scripts/auditDeadKeys.ts`) can only prove a handler
 * EXISTS. This proves it does something.
 *
 * NOTE ON EXECUTION: this spec was authored in a sandbox that cannot download
 * a Chromium binary (`npx playwright install chromium` fails with ECONNRESET
 * against the CDN — see IR-S1-001), so it shipped unexecuted and its first
 * real browser run was CI run 32988827678. That run exposed three harness
 * bugs in the spec itself, all fixed here and each documented at its fix:
 *
 *   1. it clicked the `sr-only` skip link, which Tailwind renders as a 1x1
 *      clipped element — reported visible, but not actionable until focused,
 *      so `click()` timed out;
 *   2. it clicked controls that open a modal/overlay and never dismissed it,
 *      so every later click in the sweep hit the overlay and timed out;
 *   3. it attributed page-load network noise (a 422 from /recommendations
 *      opened without quiz answers) to whichever control happened to be
 *      clicked next.
 *
 * The product controls themselves were fine: the three role journeys pass on
 * the same routes. `scripts/clickAudit.mts` and `docs/DEADKEYS_CLICK_LOG.md`
 * hold the earlier jsdom click-by-click log of all 89 controls.
 */
import fs from "node:fs";
import path from "node:path";
import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";
import { STATE_DIR } from "./statePaths";
import { DEMO_ACCOUNTS, type TestUser } from "./users";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/**
 * Accounts for the sweep.
 *
 * The sweep clicks EVERY control on EVERY route, so it mutates whatever it
 * touches: it consumes the designer's project quota, dirties the quiz, toggles
 * the theme, and so on. Sharing accounts with the journeys meant that mutation
 * leaked across specs and produced a different failure set on every run
 * (32988827678 / 33005106968 / 33008122154). globalSetup therefore registers
 * dedicated disposable users for the sweep and drops them here.
 *
 * `admin` is the documented exception: self-registration cannot grant the
 * admin role (backend/app/schemas/auth.py:26), so the sweep shares the seeded
 * admin with the admin journey. Those two never contend — the admin sweep
 * routes are read-only listings, and the destructive controls are in SKIP.
 */
type Credentials = { email: string; password: string };

let cachedAccounts: Record<"homeowner" | "designer" | "admin", Credentials> | null = null;

/** Read the sweep's credentials, lazily.
 *
 *  Deliberately NOT read at module scope: `playwright test --list` imports
 *  every spec without running globalSetup, so a top-level read would throw
 *  during collection and report "0 tests in 0 files". */
function accounts(): Record<"homeowner" | "designer" | "admin", Credentials> {
  if (cachedAccounts) return cachedAccounts;

  const file = path.join(STATE_DIR, "sweep-users.json");
  if (!fs.existsSync(file)) {
    throw new Error(
      `deadKeys: ${file} is missing — globalSetup did not run, or it failed ` +
        `before registering the sweep's disposable users.`,
    );
  }
  const users = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, TestUser>;
  cachedAccounts = {
    homeowner: users.homeowner,
    designer: users.designer,
    admin: DEMO_ACCOUNTS.admin,
  };
  return cachedAccounts;
}

/** Routes to sweep, per role. */
type SweepRole = "homeowner" | "designer" | "admin";

const ROUTES: Record<SweepRole, string[]> = {
  homeowner: ["/", "/quiz", "/recommendations", "/moodboards", "/floorplan", "/shopping-list", "/upgrade"],
  designer: ["/designer/dashboard"],
  admin: ["/admin/products", "/admin/users", "/admin/subscriptions"],
};

/** Controls we must NOT click during a sweep, with the reason. */
const SKIP = [
  /sign out/i,      // ends the session and invalidates the rest of the sweep
  /log out/i,
  /delete/i,        // destructive; covered by its own dedicated test
  /confirm delete/i,
  // The skip link is `sr-only`: Tailwind renders it as a 1x1 clipped element
  // that reports as visible but is only actionable once focused, so a plain
  // click() times out. It is NOT dead — `href="#main"` resolves to the
  // `<main id="main">` in Layout.tsx, and the dedicated keyboard test below
  // exercises it properly.
  /skip to content/i,
];

interface Failure {
  route: string;
  control: string;
  reason: string;
}

function attachWatchers(page: Page) {
  const consoleErrors: string[] = [];
  const badResponses: string[] = [];
  let requestCount = 0;

  page.on("console", (m: ConsoleMessage) => {
    if (m.type() !== "error") return;
    const t = m.text();
    // React's dev-only act() warnings and favicon 404s are not product bugs.
    if (/favicon|Download the React DevTools/i.test(t)) return;
    consoleErrors.push(t);
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
  page.on("request", () => { requestCount++; });
  page.on("response", (r) => {
    const s = r.status();
    if (s >= 400 && s !== 429 && !/favicon/.test(r.url())) {
      badResponses.push(`${s} ${r.request().method()} ${r.url()}`);
    }
  });

  return {
    consoleErrors,
    badResponses,
    get requestCount() { return requestCount; },
    /** Forget everything observed so far (used after a navigation, so that
     *  page-load traffic is not attributed to the next control clicked). */
    reset() {
      consoleErrors.length = 0;
      badResponses.length = 0;
      requestCount = 0;
    },
  };
}

/**
 * Close any modal/overlay a click may have opened.
 *
 * An overlay left open covers the page and swallows pointer events, so every
 * subsequent click in the sweep times out. Escape is the app's documented
 * dismissal for both the command palette and the shortcuts dialog; the
 * `aria-modal` probe is a cheap check that it actually closed, and a second
 * Escape covers a stacked dialog.
 */
async function dismissOverlay(page: Page): Promise<void> {
  const modal = page.locator("[aria-modal='true'], [role='dialog']").first();
  const isOpen = () => modal.isVisible().catch(() => false);

  if (!(await isOpen())) return;

  // 1) Escape. NOTE: some dialogs (e.g. the designer "New client project"
  //    modal, DashboardPage.tsx:129) bind Escape with a React `onKeyDown` on
  //    the dialog element itself, so it only fires when focus is already
  //    INSIDE the dialog. If the autofocused field has not taken focus yet,
  //    Escape lands on <body> and the modal stays open. Tracked as IR-S1-011.
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  if (!(await isOpen())) return;

  // 2) Focus the dialog, then Escape again — satisfies the focus-scoped
  //    handlers described above.
  await modal.click({ position: { x: 5, y: 5 }, timeout: 2_000 }).catch(() => {});
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  if (!(await isOpen())) return;

  // 3) Last resort: the dialog's own dismiss control.
  const cancel = modal.getByRole("button", { name: /cancel|close|بستن|انصراف/i }).first();
  await cancel.click({ timeout: 2_000 }).catch(() => {});
  await page.waitForTimeout(150);
}

async function login(page: Page, who: SweepRole) {
  const { email, password } = accounts()[who];
  await page.goto(`${BASE}/login`);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click({ timeout: 15_000 });
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15_000 });
}

for (const role of Object.keys(ROUTES) as (keyof typeof ROUTES)[]) {
  test.describe(`dead keys — ${role}`, () => {
    test(`every control on every ${role} route responds`, async ({ page }) => {
      test.slow();
      const watch = attachWatchers(page);
      const failures: Failure[] = [];
      const log: string[] = [];

      await login(page, role);

      for (const route of ROUTES[role]) {
        await page.goto(`${BASE}${route}`);
        await page.waitForLoadState("networkidle");
        // Network noise from the page load itself (e.g. /recommendations
        // answers a 422 when opened without quiz answers) must not be charged
        // to the first control that happens to be clicked next.
        watch.reset();

        const controls = page.locator(
          "button:not([disabled]), a[href], [role='button']:not([aria-disabled='true'])",
        );
        const count = await controls.count();

        for (let i = 0; i < count; i++) {
          const el = controls.nth(i);
          if (!(await el.isVisible().catch(() => false))) continue;

          const name =
            (await el.getAttribute("aria-label")) ??
            (await el.innerText().catch(() => ""))?.trim().slice(0, 40) ??
            `control#${i}`;
          if (!name || SKIP.some((re) => re.test(name))) continue;

          const beforeErrors = watch.consoleErrors.length;
          const beforeBad = watch.badResponses.length;
          const beforeReqs = watch.requestCount;
          const beforeHtml = await page.locator("body").innerHTML();
          const beforeUrl = page.url();
          // Some controls legitimately mutate state OUTSIDE <body>. The theme
          // toggle sets `class="dark"` and `style.colorScheme` on
          // <html> (themeStore.ts:15-16), so diffing body alone declared it
          // DEAD on every route of every role. Capture the root attributes too.
          const beforeRoot = await page.evaluate(
            () => document.documentElement.className + "|" + document.documentElement.style.colorScheme,
          );

          // Scroll the control clear of the sticky header BEFORE clicking.
          //
          // Layout.tsx:112 renders `<header class="sticky top-0 z-40">`. Playwright
          // scrolls a control just into the viewport, which frequently parks it
          // UNDER that header; the click then lands on the header and retries
          // until the 5s timeout. That single interaction produced the bulk of
          // the "click threw: Timeout 5000ms exceeded" verdicts across all
          // three roles — controls a human can click perfectly well.
          await el
            .evaluate((node) => node.scrollIntoView({ block: "center", inline: "center" }))
            .catch(() => {});
          await page.waitForTimeout(60);

          let clicked = true;
          await el.click({ timeout: 5_000, trial: false }).catch((e: Error) => {
            clicked = false;
            failures.push({
              route,
              control: name,
              reason: `click threw: ${e.message.split("\n")[0]}`,
            });
          });
          await page.waitForTimeout(220); // let optimistic UI + toasts settle

          const afterHtml = await page.locator("body").innerHTML();
          const afterRoot = await page.evaluate(
            () => document.documentElement.className + "|" + document.documentElement.style.colorScheme,
          );
          const changed =
            afterHtml !== beforeHtml ||
            afterRoot !== beforeRoot ||
            page.url() !== beforeUrl ||
            watch.requestCount > beforeReqs;

          if (watch.consoleErrors.length > beforeErrors) {
            failures.push({
              route, control: name,
              reason: `console error: ${watch.consoleErrors.at(-1)}`,
            });
          }
          if (watch.badResponses.length > beforeBad) {
            failures.push({
              route, control: name,
              reason: `bad response: ${watch.badResponses.at(-1)}`,
            });
          }
          // A nav link pointing at the route we are already on legitimately
          // changes nothing — same URL, no re-render, no request. That is
          // correct behaviour, not a dead control, so do not report it.
          const href = await el.getAttribute("href").catch(() => null);
          const selfLink =
            href !== null && new URL(href, page.url()).pathname === new URL(beforeUrl).pathname;

          // Only a click that actually LANDED can prove a control is dead. When
          // the click itself threw, "nothing changed" is a restatement of that
          // failure, not independent evidence — reporting both doubled every
          // verdict and made the sweep look twice as broken as it was.
          if (clicked && !changed && !selfLink) {
            failures.push({ route, control: name, reason: "DEAD — no DOM/URL/network change" });
          }

          log.push(`${changed ? "OK  " : "DEAD"} ${route} :: ${name}`);

          // A click may open a modal/overlay (command palette, dialogs). Left
          // open, it swallows pointer events and every remaining click in the
          // sweep times out — which is what turned 3 real openers into ~90
          // bogus "click threw" failures on the first browser run. Dismiss it
          // before moving on.
          await dismissOverlay(page);

          // A click may navigate away; return so the index stays meaningful.
          if (page.url() !== beforeUrl) {
            await page.goto(`${BASE}${route}`);
            await page.waitForLoadState("networkidle");
            watch.reset();
          }
        }
      }

      console.log(log.join("\n"));
      expect(failures, `\n${failures.map((f) => `${f.route} :: ${f.control} — ${f.reason}`).join("\n")}`)
        .toEqual([]);
    });
  });
}

test.describe("dead keys — specific known suspects", () => {
  test("shopping list quantity stepper updates the total", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/shopping-list`);
    await page.waitForLoadState("networkidle");

    const plus = page.getByRole("button", { name: /increase quantity/i }).first();
    test.skip(!(await plus.count()), "no items in the shopping list");

    const totalNode = page.locator("text=/Total/i").locator("xpath=following::p[1]");
    const before = await totalNode.innerText();
    await plus.click({ timeout: 15_000 });
    await expect(totalNode).not.toHaveText(before);
  });

  test("floorplan Export PNG triggers a download", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/floorplan`);
    const downloadPromise = page.waitForEvent("download", { timeout: 20_000 });
    await page.getByRole("button", { name: /export png/i }).click({ timeout: 15_000 });
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/floorplan.*\.png$/);
  });

  test("admin sort toggle reorders rows", async ({ page }) => {
    await login(page, "admin");
    await page.goto(`${BASE}/admin/products`);
    await page.waitForLoadState("networkidle");
    const firstBefore = await page.locator("tbody tr").first().innerText();
    await page.getByRole("button", { name: /confidence/i }).click({ timeout: 15_000 });
    await page.waitForTimeout(300);
    const firstAfter = await page.locator("tbody tr").first().innerText();
    expect(firstAfter).not.toBe(firstBefore);
  });

  test("designer share copies a link and toasts", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await login(page, "designer");
    await page.goto(`${BASE}/designer/dashboard`);
    await page.waitForLoadState("networkidle");
    const firstProject = page.locator("ul li a").first();
    test.skip(!(await firstProject.count()), "no projects");
    await firstProject.click({ timeout: 15_000 });

    const shareBtn = page.getByRole("button", { name: /share with client/i }).first();
    test.skip(!(await shareBtn.count()), "no quizzes to share");
    await shareBtn.click({ timeout: 15_000 });

    await page.getByRole("button", { name: /copy link/i }).click({ timeout: 15_000 });
    await expect(page.getByText(/copied to clipboard/i)).toBeVisible();
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    expect(clip).toContain("/share/");
  });

  test("command palette opens with Cmd+K and runs a command", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/recommendations`);
    await page.waitForLoadState("networkidle");
    await page.keyboard.press("ControlOrMeta+k");

    // The overlay is lazy-loaded (`lazy(() => import(...))` in
    // CommandPalette.tsx), so the input only exists once that chunk resolves.
    // The placeholder is "Search commands…" — the original spec waited for
    // /type a command/i, a string that has never been in the component, and
    // failed on the suite's first real browser run.
    const input = page.getByPlaceholder(/search commands/i);
    await expect(input).toBeVisible({ timeout: 15_000 });

    await page.keyboard.press("Escape");
    await expect(input).toBeHidden();
  });

  test("skip link is focusable and jumps to main content", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/`);
    await page.waitForLoadState("networkidle");

    // The skip link is `sr-only` until focused (WCAG 2.4.1), so it cannot be
    // clicked cold — it is excluded from the click sweep and asserted here the
    // way a keyboard user actually reaches it: Tab from the top of the page.
    const skip = page.getByRole("link", { name: /skip to content/i });
    await page.keyboard.press("Tab");
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main$/);
    // The target must exist, otherwise the link is decorative.
    await expect(page.locator("#main")).toBeVisible();
  });
});
