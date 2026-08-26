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
 * here, before any test that depends on a session runs.
 *
 * Rate-limit note: the backend allows 5 logins/min per IP (`login:{ip}`).
 * Three sequential logins is well inside that budget, but they are performed
 * one at a time (never in parallel) so a retry has headroom.
 */
import path from "node:path";
import { chromium, type FullConfig } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** Seeded demo accounts (SEED_DEMO_ACCOUNTS=true, never in production).
 *  See docs/security/DEMO_ACCOUNTS.md. */
export const DEMO_ACCOUNTS = {
  homeowner: { email: "demo@smartdecor.dev", password: "Demo1234!" },
  designer: { email: "designer@smartdecor.dev", password: "Design123!" },
  admin: { email: "admin@smartdecor.dev", password: "Admin123!" },
} as const;

type Role = keyof typeof DEMO_ACCOUNTS;

/** Where each role's storageState lives, relative to the Playwright rootDir. */
export function statePath(rootDir: string, role: Role): string {
  return path.join(rootDir, "test-results", "state", `${role}.json`);
}

export default async function globalSetup(config: FullConfig) {
  const browser = await chromium.launch();
  try {
    for (const role of Object.keys(DEMO_ACCOUNTS) as Role[]) {
      const account = DEMO_ACCOUNTS[role];
      const context = await browser.newContext();
      const page = await context.newPage();
      try {
        await page.goto(`${BASE}/login`);
        await page.getByLabel(/email/i).fill(account.email);
        await page.getByLabel(/password/i).fill(account.password);
        await page.getByRole("button", { name: /sign in/i }).click();
        // A working login navigates away from /login to the role destination
        // (homeowner -> /quiz, designer -> /designer/dashboard,
        //  admin -> /admin/products; see LoginPage.tsx).
        await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 20_000 });

        await context.storageState({ path: statePath(config.rootDir, role) });
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}
