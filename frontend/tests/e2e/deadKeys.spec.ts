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
 * NOTE ON EXECUTION: the sandbox this was authored in cannot download a
 * Chromium binary (`npx playwright install chromium` fails with ECONNRESET
 * against the CDN), so this spec is committed as the CI gate but was not run
 * here. The equivalent assertions were executed in a jsdom harness instead —
 * see `scripts/clickAudit.mts` and `docs/DEADKEYS_CLICK_LOG.md` for the real
 * click-by-click log of all 89 controls.
 */
import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

const ACCOUNTS = {
  homeowner: { email: "demo@smartdecor.dev", password: "Demo1234!" },
  designer: { email: "designer@smartdecor.dev", password: "Design123!" },
  admin: { email: "admin@smartdecor.dev", password: "Admin123!" },
};

/** Routes to sweep, per role. */
const ROUTES: Record<keyof typeof ACCOUNTS, string[]> = {
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
  };
}

async function login(page: Page, who: keyof typeof ACCOUNTS) {
  const { email, password } = ACCOUNTS[who];
  await page.goto(`${BASE}/login`);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
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

          await el.click({ timeout: 5_000, trial: false }).catch(() => {
            failures.push({ route, control: name, reason: "click threw" });
          });
          await page.waitForTimeout(220); // let optimistic UI + toasts settle

          const afterHtml = await page.locator("body").innerHTML();
          const changed =
            afterHtml !== beforeHtml ||
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
          if (!changed) {
            failures.push({ route, control: name, reason: "DEAD — no DOM/URL/network change" });
          }

          log.push(`${changed ? "OK  " : "DEAD"} ${route} :: ${name}`);

          // A click may navigate away; return so the index stays meaningful.
          if (page.url() !== beforeUrl) {
            await page.goto(`${BASE}${route}`);
            await page.waitForLoadState("networkidle");
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
    await plus.click();
    await expect(totalNode).not.toHaveText(before);
  });

  test("floorplan Export PNG triggers a download", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/floorplan`);
    const downloadPromise = page.waitForEvent("download", { timeout: 20_000 });
    await page.getByRole("button", { name: /export png/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/floorplan.*\.png$/);
  });

  test("admin sort toggle reorders rows", async ({ page }) => {
    await login(page, "admin");
    await page.goto(`${BASE}/admin/products`);
    await page.waitForLoadState("networkidle");
    const firstBefore = await page.locator("tbody tr").first().innerText();
    await page.getByRole("button", { name: /confidence/i }).click();
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
    await firstProject.click();

    const shareBtn = page.getByRole("button", { name: /share with client/i }).first();
    test.skip(!(await shareBtn.count()), "no quizzes to share");
    await shareBtn.click();

    await page.getByRole("button", { name: /copy link/i }).click();
    await expect(page.getByText(/copied to clipboard/i)).toBeVisible();
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    expect(clip).toContain("/share/");
  });

  test("command palette opens with Cmd+K and runs a command", async ({ page }) => {
    await login(page, "homeowner");
    await page.goto(`${BASE}/recommendations`);
    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByPlaceholder(/type a command/i)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByPlaceholder(/type a command/i)).toBeHidden();
  });
});
