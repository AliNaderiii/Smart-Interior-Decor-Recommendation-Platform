import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config (Stage 1, T-1.4 + T-1.4 close-out).
 *
 *  Assumes the dev server and API are already up (the sandbox runs them as
 *  long-lived processes; CI starts both in the e2e job); set E2E_BASE_URL to
 *  point elsewhere.
 *
 *  Projects:
 *   chromium             — anonymous context: the dead-key sweep plus the auth
 *                          NEGATIVE tests (XSS / redirect on bad login)
 *   chromium-homeowner   — homeowner session (storageState from globalSetup):
 *                          auth smoke + the full homeowner journey
 *   chromium-designer    — designer session: projects dashboard, create
 *                          project, quota wall
 *   chromium-admin       — admin session: product upload/review/approve,
 *                          users and subscriptions
 *
 *  The role projects depend on `setup-state` implicitly: globalSetup writes
 *  all three storageState files before any project runs.
 */
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // the sweep and the journeys mutate shared server state
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/e2e-report.json" }],
    ["html", { outputFolder: "test-results/html", open: "never" }],
  ],
  globalSetup: "./tests/e2e/globalSetup.ts",
  outputDir: "./test-results/artifacts",
  use: {
    baseURL: BASE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testMatch: ["deadKeys.spec.ts", "auth-negative.spec.ts"],
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-homeowner",
      testMatch: ["auth-smoke.spec.ts", "journey-homeowner.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "test-results/state/homeowner.json",
      },
    },
    {
      name: "chromium-designer",
      testMatch: ["journey-designer.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "test-results/state/designer.json",
      },
    },
    {
      name: "chromium-admin",
      testMatch: ["journey-admin.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "test-results/state/admin.json",
      },
    },
  ],
});
