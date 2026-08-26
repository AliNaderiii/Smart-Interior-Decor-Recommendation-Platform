/**
 * Playwright global setup (Stage 1, T-1.4 + T-1.4 close-out).
 *
 * Creates the AUTHENTICATED sessions the role-scoped projects need. Each one
 * walks the REAL login UI with a seeded demo account and persists the
 * resulting storageState (cookies — including the httpOnly pair the backend
 * issues — plus localStorage) to disk:
 *
 *   chromium-homeowner  <- test-results/state/homeowner.json
 *   chromium-designer   <- test-results/state/designer.json
 *   chromium-admin      <- test-results/state/admin.json
 *
 * Side benefit: if the login flow itself is broken, the whole e2e job fails
 * here, before any test that depends on a session runs — and it fails LOUDLY,
 * with the URL, the visible page error and a screenshot, instead of letting
 * every role project die later with an opaque ENOENT on a missing state file
 * (which is exactly what CI run 32988827678 did).
 *
 * Rate-limit note: the backend allows 5 logins/min per IP (`login:{ip}`).
 * Three sequential logins is well inside that budget, but they are performed
 * one at a time (never in parallel) so a retry has headroom.
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";
import { STATE_DIR, statePath, type Role } from "./statePaths";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** Seeded demo accounts (SEED_DEMO_ACCOUNTS=true, never in production).
 *  See docs/security/DEMO_ACCOUNTS.md. */
export const DEMO_ACCOUNTS = {
  homeowner: { email: "demo@smartdecor.dev", password: "Demo1234!" },
  designer: { email: "designer@smartdecor.dev", password: "Design123!" },
  admin: { email: "admin@smartdecor.dev", password: "Admin123!" },
} as const;

export default async function globalSetup() {
  // The projects read these files; make sure the directory exists even if a
  // previous run cleaned test-results away.
  fs.mkdirSync(STATE_DIR, { recursive: true });

  const browser = await chromium.launch();
  try {
    for (const role of Object.keys(DEMO_ACCOUNTS) as Role[]) {
      const account = DEMO_ACCOUNTS[role];
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
          // Fail with something a CI reader can act on: where we ended up and
          // what the page said. Without this the only symptom is a later
          // ENOENT on the state file, which says nothing about the cause.
          const shot = path.join(STATE_DIR, `login-failed-${role}.png`);
          await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
          const message = await page
            .getByRole("alert")
            .first()
            .textContent({ timeout: 2_000 })
            .catch(() => null);
          throw new Error(
            `globalSetup: ${role} login did not leave /login.\n` +
              `  account : ${account.email}\n` +
              `  url     : ${page.url()}\n` +
              `  page says: ${message?.trim() || "(no alert rendered)"}\n` +
              `  screenshot: ${shot}\n` +
              `Check that the API is reachable and SEED_DEMO_ACCOUNTS=true seeded this account.`,
          );
        }

        const target = statePath(role);
        await context.storageState({ path: target });
        // Prove the artifact the projects depend on actually exists now.
        if (!fs.existsSync(target)) {
          throw new Error(`globalSetup: storageState for ${role} was not written to ${target}`);
        }
        console.log(`globalSetup: ${role} session -> ${target}`);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}
