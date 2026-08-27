/**
 * Authenticated homepage smoke (Stage 1, T-1.4) — runs in the
 * `chromium-authenticated` project, whose session comes from the
 * storageState written by globalSetup.ts (real UI login, demo homeowner).
 *
 * The point of this spec: a valid session (httpOnly cookies) must actually
 * be USABLE — home page paints, auth-gated routes open without bouncing to
 * /login. (This is exactly the property the T-1.4 guard fix restores in the
 * default USE_COOKIE_AUTH=true mode.)
 */
import { test, expect } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

test.describe("authenticated smoke (storageState session)", () => {
  test("logged-in homeowner lands on the homepage, not the login wall", async ({ page }) => {
    await page.goto(`${BASE}/`);
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/$/);
    // The homepage is a public route — assert it is not the login card and
    // not an auth-wall redirect.
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);
    // The app header is present (brand + navigation), proving a real paint.
    await expect(page.locator("header").first()).toBeVisible();
    // No unhandled failures while the home page settles.
  });

  test("auth-gated /quiz opens for the session (cookie mode, no local tokens)", async ({ page }) => {
    await page.goto(`${BASE}/quiz`);
    await page.waitForLoadState("networkidle");

    // The regression this spec guards: before the T-1.4 guard fix, a
    // cookie-mode session had no localStorage token and was bounced here.
    await expect(page).toHaveURL(/\/quiz/);
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);

    // The quiz UI actually painted (first step content), not a spinner
    // that never resolves.
    await expect(page.getByRole("button", { name: /next|continue|التالي/i }).first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("session survives a full page reload (cookies re-sent on fresh load)", async ({ page }) => {
    await page.goto(`${BASE}/moodboards`);
    await page.waitForLoadState("networkidle");
    // If this lands on /login the session died before the reload was even
    // attempted, which is a different failure from the one under test. Say so,
    // because the bare URL mismatch reads as a product bug and is not one:
    // see IR-S1-012 (refresh-token rotation vs a shared storageState).
    if (new URL(page.url()).pathname.startsWith("/login")) {
      throw new Error(
        "auth-smoke: the storageState session was already invalid before the " +
          "reload step. Expected /moodboards, got /login. This usually means " +
          "the access token in the snapshot expired mid-suite and its refresh " +
          "token was already rotated away by an earlier test — see IR-S1-012 " +
          "and ACCESS_TOKEN_EXPIRE_MINUTES in the e2e job.",
      );
    }
    await expect(page).toHaveURL(/\/moodboards/);
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/moodboards/);
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);
  });
});
