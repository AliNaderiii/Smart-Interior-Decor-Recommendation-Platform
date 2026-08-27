/**
 * Playwright global setup (Stage 1, T-1.4 + T-1.4 close-out).
 *
 * Creates the AUTHENTICATED sessions the role-scoped projects need and
 * persists each one's storageState (cookies — including the httpOnly pair the
 * backend issues — plus localStorage) to disk:
 *
 *   chromium-homeowner  <- test-results/state/homeowner.json
 *   chromium-designer   <- test-results/state/designer.json
 *   chromium-admin      <- test-results/state/admin.json
 *   chromium (sweep)    <- test-results/state/sweep-{homeowner,designer}.json
 *
 * ISOLATION (the structural fix for the flaky suite)
 * --------------------------------------------------
 * Every session except admin is a DISPOSABLE account registered here with a
 * unique `@example.com` address — see `users.ts` for the full rationale. The
 * dead-key sweep gets its OWN accounts, separate from the journeys', because
 * the sweep clicks every control on every route and therefore mutates state
 * (it consumes the designer project quota, dirties the quiz, and so on). With
 * shared accounts that mutation leaked into the journeys, which is why runs
 * 32988827678 / 33005106968 / 33008122154 each failed a different subset of
 * tests from nearly identical code.
 *
 * Admin stays on the seeded account: `POST /auth/register` refuses
 * `role=admin` (backend/app/schemas/auth.py:26), and the admin journey is
 * asserting against the seeded catalogue anyway.
 *
 * Sessions are established via the login UI, so a broken login flow fails the
 * whole job HERE, loudly (URL + on-page error + screenshot), rather than
 * surfacing later as an opaque ENOENT on a missing state file.
 *
 * Rate limits: registration and login are both per-IP throttled
 * (`register:{ip}`, `login:{ip}`). This setup performs 4 registrations and
 * 5 logins sequentially, so the e2e job raises both limits — see
 * `ci/ci.stage1.yml` and the hand-off note in the Stage 1 report.
 */
import fs from "node:fs";
import path from "node:path";
import { chromium, type Browser } from "@playwright/test";
import { STATE_DIR, statePath } from "./statePaths";
import { DEMO_ACCOUNTS, makeUser, registerUser, type TestUser } from "./users";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** Re-exported so specs that still need the seeded identities can import them
 *  from one place. */
export { DEMO_ACCOUNTS };

/**
 * Wait until the API answers, so a slow backend surfaces as "the API never
 * came up" instead of a confusing registration or login failure.
 */
async function waitForApi(timeoutMs = 120_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "never attempted";

  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE}/api/v1/health`);
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }

  throw new Error(
    `globalSetup: the API behind ${BASE} never became healthy ` +
      `(${Math.round(timeoutMs / 1000)}s). Last attempt: ${lastError}`,
  );
}

/** Log in through the real UI and persist the session to `stateFile`. */
async function saveSession(
  browser: Browser,
  account: { email: string; password: string },
  stateFile: string,
  label: string,
): Promise<void> {
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });

    // Wait for the form to be interactive (React has hydrated) rather than
    // typing into markup that is about to be replaced.
    const email = page.getByLabel(/email/i);
    await email.waitFor({ state: "visible", timeout: 60_000 });

    await email.fill(account.email);
    await page.getByLabel(/password/i).fill(account.password);
    await page.getByRole("button", { name: /sign in/i }).click();

    // A working login navigates away from /login to the role destination
    // (homeowner -> /quiz, designer -> /designer/dashboard,
    //  admin -> /admin/products; see LoginPage.tsx).
    try {
      await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 20_000 });
    } catch {
      // Fail with something a CI reader can act on: where we ended up and what
      // the page said. Without this the only symptom is a later ENOENT on the
      // state file, which says nothing about the cause.
      const shot = path.join(STATE_DIR, `login-failed-${label}.png`);
      await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
      const message = await page
        .getByRole("alert")
        .first()
        .textContent({ timeout: 2_000 })
        .catch(() => null);
      throw new Error(
        `globalSetup: ${label} login did not leave /login.\n` +
          `  account : ${account.email}\n` +
          `  url     : ${page.url()}\n` +
          `  page says: ${message?.trim() || "(no alert rendered)"}\n` +
          `  screenshot: ${shot}\n` +
          `Check that the API is reachable and, for the seeded admin, that ` +
          `SEED_DEMO_ACCOUNTS=true ran.`,
      );
    }

    await context.storageState({ path: stateFile });

    // Prove the artifact the projects depend on actually exists now.
    if (!fs.existsSync(stateFile)) {
      throw new Error(`globalSetup: storageState for ${label} was not written to ${stateFile}`);
    }
    console.log(`globalSetup: ${label} session (${account.email}) -> ${stateFile}`);
  } finally {
    await context.close();
  }
}

export default async function globalSetup() {
  // The projects read these files; make sure the directory exists even if a
  // previous run cleaned test-results away.
  fs.mkdirSync(STATE_DIR, { recursive: true });

  await waitForApi();

  // Disposable identities: one per journey role, plus one per sweep role.
  const journeyHomeowner = makeUser("homeowner", "journey");
  const journeyDesigner = makeUser("designer", "journey");
  const sweepHomeowner = makeUser("homeowner", "sweep");
  const sweepDesigner = makeUser("designer", "sweep");

  const disposable: TestUser[] = [
    journeyHomeowner,
    journeyDesigner,
    sweepHomeowner,
    sweepDesigner,
  ];

  // Register sequentially — the per-IP registration limit is a rate, and a
  // burst buys nothing here.
  for (const user of disposable) {
    await registerUser(BASE, user);
    console.log(`globalSetup: registered ${user.role} ${user.email}`);
  }

  // Hand the sweep its accounts. It logs in through the UI itself (it asserts
  // on the login flow as part of the sweep), so it needs the credentials, not
  // a storageState.
  fs.writeFileSync(
    path.join(STATE_DIR, "sweep-users.json"),
    JSON.stringify({ homeowner: sweepHomeowner, designer: sweepDesigner }, null, 2),
  );

  const browser = await chromium.launch();
  try {
    await saveSession(browser, journeyHomeowner, statePath("homeowner"), "homeowner");
    await saveSession(browser, journeyDesigner, statePath("designer"), "designer");
    // Admin cannot be self-registered; see users.ts.
    await saveSession(browser, DEMO_ACCOUNTS.admin, statePath("admin"), "admin");
  } finally {
    await browser.close();
  }
}
