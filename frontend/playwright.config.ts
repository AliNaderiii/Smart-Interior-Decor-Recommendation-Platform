import { defineConfig, devices } from "@playwright/test";

/** Phase 4 dead-keys e2e.
 *
 *  Assumes the dev server and API are already up (the sandbox runs them as
 *  long-lived processes); set E2E_BASE_URL to point elsewhere. */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // the sweep mutates shared server state
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/deadkeys.json" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
