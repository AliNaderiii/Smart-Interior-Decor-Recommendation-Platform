/**
 * Designer (B2B2C) end-to-end journey (Stage 1, T-1.4 close-out).
 *
 * Contractual scope covered (client advertisement, Portal 2):
 *   professional projects dashboard -> create project (201 path) ->
 *   multiple project management -> "subscription required to create new
 *   projects": the quota wall (402) must be VISIBLE to the designer.
 *
 * Runs in the `chromium-designer` project (storageState from globalSetup,
 * designer@smartdecor.dev).
 *
 * Quota model under test (T-1.1): the seeded designer has no active
 * subscription, so they inherit the `designer_free` dataset quota of 2
 * projects (backend/seed_data/subscription_plans.json). The 3rd POST
 * /projects returns 402 with the Persian message from
 * app/services/designer_quota.py.
 *
 * IMPORTANT — this spec is stateful by design: the seeded designer starts
 * with 0 projects in a fresh CI database, so it creates exactly up to the
 * quota and then asserts the wall. It cleans up after itself via the UI-less
 * DELETE endpoint so a re-run against a persistent database still starts from
 * a known state.
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** The designer free-plan quota from the seed dataset. Kept as a constant so
 *  a dataset change makes this spec fail loudly rather than silently drift. */
const FREE_PLAN_QUOTA = 2;

/** Fragment of the backend's Persian 402 message (designer_quota.py). Matching
 *  a fragment rather than the whole sentence keeps this robust to the plan
 *  name and the numeric limit being interpolated. */
const QUOTA_MESSAGE = /سهمیهٔ پروژه‌های شما/;

const RUN = Date.now();

/** Create a project through the real dashboard modal. Returns after the
 *  mutation settles (either the modal closes on success, or a toast appears). */
async function createProjectViaUi(page: Page, name: string) {
  await page.getByRole("button", { name: /^new project$/i }).click();
  const dialog = page.getByRole("dialog", { name: /create project/i });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel(/project name/i).fill(name);
  await dialog.getByLabel(/^client name$/i).fill("E2E Client");
  await dialog.getByRole("button", { name: /^create$/i }).click();
}

/** Delete every project this run created, straight through the API using the
 *  browser's own session (cookies + the double-submit CSRF header the backend
 *  requires for cookie auth). Keeps re-runs idempotent. */
async function cleanup(page: Page, request: APIRequestContext) {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrf_token")?.value ?? "";
  const listed = await request.get(`${BASE}/api/v1/projects`, {
    headers: { "X-CSRF-Token": csrf },
  });
  if (!listed.ok()) return;
  const body = (await listed.json()) as { data?: { id: string; name: string }[] };
  for (const project of body.data ?? []) {
    if (project.name.startsWith("E2E ")) {
      await request.delete(`${BASE}/api/v1/projects/${project.id}`, {
        headers: { "X-CSRF-Token": csrf },
      });
    }
  }
}

test.describe.serial("designer journey", () => {
  test.afterAll(async ({ browser, request }) => {
    const context = await browser.newContext({
      storageState: "test-results/state/designer.json",
    });
    const page = await context.newPage();
    await page.goto(`${BASE}/designer/dashboard`);
    await cleanup(page, request);
    await context.close();
  });

  test("the projects dashboard loads for a designer session", async ({ page, request }) => {
    await page.goto(`${BASE}/designer/dashboard`);
    await expect(page).toHaveURL(/\/designer\/dashboard/);
    await expect(page.getByRole("heading", { name: /^projects$/i })).toBeVisible({
      timeout: 30_000,
    });
    // Not the login wall — the designer role really passes RequireAuth.
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);
    // The primary action of the portal is present.
    await expect(page.getByRole("button", { name: /^new project$/i })).toBeVisible();

    // Start from a known state so the quota assertions below are meaningful.
    await cleanup(page, request);
  });

  test("creates projects up to the free-plan quota (201 path)", async ({ page }) => {
    await page.goto(`${BASE}/designer/dashboard`);
    await expect(page.getByRole("button", { name: /^new project$/i })).toBeVisible({
      timeout: 30_000,
    });

    for (let i = 1; i <= FREE_PLAN_QUOTA; i++) {
      const name = `E2E Project ${RUN}-${i}`;
      await createProjectViaUi(page, name);
      // Success closes the modal and the new row appears in the list.
      await expect(page.getByRole("dialog", { name: /create project/i })).toHaveCount(0, {
        timeout: 20_000,
      });
      await expect(page.getByText(name, { exact: true })).toBeVisible({ timeout: 20_000 });
    }

    // Multiple project management: both rows coexist and are navigable links.
    for (let i = 1; i <= FREE_PLAN_QUOTA; i++) {
      await expect(page.getByRole("link", { name: new RegExp(`E2E Project ${RUN}-${i}`) })).toBeVisible();
    }
  });

  test("the quota wall is visible: the 402 Persian message surfaces in the UI", async ({
    page,
  }) => {
    await page.goto(`${BASE}/designer/dashboard`);
    await expect(page.getByRole("button", { name: /^new project$/i })).toBeVisible({
      timeout: 30_000,
    });

    // Watch the wire so the test proves the backend really refused, not just
    // that some toast happened to appear.
    const quotaResponse = page.waitForResponse(
      (r) => r.url().includes("/api/v1/projects") && r.request().method() === "POST",
      { timeout: 30_000 },
    );

    await createProjectViaUi(page, `E2E Project ${RUN}-over-quota`);

    const response = await quotaResponse;
    expect(response.status(), "3rd project should be refused with 402").toBe(402);
    const body = (await response.json()) as { success: boolean; error: string };
    expect(body.success).toBe(false);
    expect(body.error).toMatch(QUOTA_MESSAGE);

    // The DoD: the designer can actually READ why. The toast region is
    // role="status" (Toast.tsx) and must carry the server's Persian sentence.
    // (Stage 1 T-1.4 close-out fixed DashboardPage to stop replacing this
    //  with a generic English string.)
    await expect(page.getByRole("status").getByText(QUOTA_MESSAGE)).toBeVisible({
      timeout: 15_000,
    });

    // And nothing was created behind the wall.
    await expect(page.getByText(`E2E Project ${RUN}-over-quota`, { exact: true })).toHaveCount(0);
  });
});
