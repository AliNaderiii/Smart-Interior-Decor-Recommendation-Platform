import { defineConfig, devices } from "@playwright/test";
import { ANONYMOUS_STATE_PATH, statePath } from "./tests/e2e/statePaths";

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
 *  Locale: the UI defaults to Persian, the specs are written against the
 *  English catalogue. globalSetup pins `smartdecor.locale` into every
 *  storageState (role and anonymous alike) — see tests/e2e/locale.ts.
 *
 *  The role projects depend on globalSetup implicitly: it writes all three
 *  storageState files before any project runs. Those paths come from
 *  `tests/e2e/statePaths.ts` and are ABSOLUTE on purpose — a relative
 *  `storageState` is resolved against `process.cwd()` while globalSetup used
 *  to resolve against `config.rootDir` (= testDir), and the two disagreed,
 *  which is what produced the auth-smoke ENOENT in CI run 32988827678.
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
    // Emits failures as ::error:: annotations so a red CI job is diagnosable
    // without downloading the report artifact (no-op outside GitHub Actions).
    ["./tests/e2e/ciAnnotationReporter.ts"],
    ["json", { outputFile: "test-results/e2e-report.json" }],
    ["html", { outputFolder: "test-results/html", open: "never" }],
  ],
  globalSetup: "./tests/e2e/globalSetup.ts",
  outputDir: "./test-results/artifacts",
  use: {
    baseURL: BASE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Safety net: no single locator action may wait longer than this. Without
    // it, an auto-waiting call on an element that left the DOM (see the
    // deadKeys `href` note) blocks until the TEST timeout — 12 minutes of CI
    // for one vanished link. Specs that need longer pass an explicit timeout.
    actionTimeout: 30_000,
  },
  projects: [
    {
      // Anonymous context, BLOCKING. The Stage-1 auth negatives live here.
      name: "chromium",
      testMatch: ["auth-negative.spec.ts"],
      // No session — but the locale must still be pinned, or the login form
      // renders in Persian and `/sign in/i` never matches (see locale.ts).
      use: { ...devices["Desktop Chrome"], storageState: ANONYMOUS_STATE_PATH },
    },
    {
      // The legacy dead-key sweep, split into its own project so its verdicts
      // can be waived (IR-S1-013) without weakening any Stage-1 spec. See the
      // `--forbid-only`-style guard in the e2e job: this project is the ONLY
      // one allowed to be non-blocking.
      name: "chromium-sweep",
      testMatch: ["deadKeys.spec.ts"],
      use: { ...devices["Desktop Chrome"], storageState: ANONYMOUS_STATE_PATH },
    },
    {
      name: "chromium-homeowner",
      testMatch: ["auth-smoke.spec.ts", "journey-homeowner.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: statePath("homeowner"),
      },
    },
    {
      name: "chromium-designer",
      testMatch: ["journey-designer.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: statePath("designer"),
      },
    },
    {
      name: "chromium-admin",
      testMatch: ["journey-admin.spec.ts"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: statePath("admin"),
      },
    },
  ],
});
