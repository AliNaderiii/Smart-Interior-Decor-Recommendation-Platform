/**
 * Auth negative e2e (Stage 1, T-1.4) — runs as an ANONYMOUS context.
 *
 * "Bad login must be boring": an injected script never executes, the user is
 * never redirected (especially not to an admin route), and a generic, safe
 * error is shown. A unique (unregistered) email keeps these probes from
 * consuming the demo account's brute-force budget (5 fails -> 15 min lockout).
 */
import { test, expect, type Page } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** If anything reflects this as HTML or runs it, a test fails. */
const XSS_PAYLOAD = '<img src=x onerror="window.__xss_fired=true">';

function watchXss(page: Page) {
  let dialogFired = false;
  page.on("dialog", async (d) => {
    dialogFired = true;
    await d.dismiss().catch(() => {});
  });
  page.on("pageerror", () => {
    // A page-level exception during login is a product bug — record it.
    dialogFired = true;
  });
  return {
    get dialogFired() {
      return dialogFired;
    },
    async probe() {
      return page.evaluate(() => ({
        xssFlag: (window as unknown as { __xss_fired?: boolean }).__xss_fired === true,
        liveImg: !!document.querySelector('img[src="x"]'),
      }));
    },
  };
}

test.describe("auth negatives (anonymous)", () => {
  test("XSS payload in the login form never executes and never redirects", async ({ page }) => {
    const xss = watchXss(page);
    await page.goto(`${BASE}/login`);

    const uniqueEmail = `xss-probe-${Date.now()}@example.com`;
    await page.getByLabel(/email/i).fill(uniqueEmail);
    await page.getByLabel(/password/i).fill(XSS_PAYLOAD);
    await page.getByRole("button", { name: /sign in/i }).click();

    // A safe, generic error is shown (server: "Invalid credentials").
    await expect(
      page.locator("p", { hasText: /invalid credentials|login failed/i }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Still on /login — no redirect anywhere, least of all to admin.
    await expect(page).toHaveURL(/\/login$/);
    expect(new URL(page.url()).pathname).not.toMatch(/^\/(admin|quiz|designer)/);

    // No script execution: no dialog, no onerror flag, no live <img src=x>.
    expect(xss.dialogFired).toBe(false);
    const probe = await xss.probe();
    expect(probe.xssFlag).toBe(false);
    expect(probe.liveImg).toBe(false);
    // The payload may exist as an escaped INPUT value — never as live HTML.
    const bodyHtml = await page.locator("body").innerHTML();
    expect(bodyHtml).not.toContain('<img src=x onerror=');
  });

  test("wrong password on the real demo account: generic error, no redirect, no tokens", async ({
    page,
    context,
  }) => {
    const xss = watchXss(page);
    await page.goto(`${BASE}/login`);

    await page.getByLabel(/email/i).fill("demo@smartdecor.dev");
    await page.getByLabel(/password/i).fill("DefinitelyWrong1!");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.locator("p", { hasText: /invalid credentials|login failed/i }).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page).toHaveURL(/\/login$/);
    expect(xss.dialogFired).toBe(false);

    // No credential may have been issued: no auth cookies, no localStorage
    // token pair for a failed login.
    const cookies = await context.cookies();
    expect(cookies.map((c) => c.name)).not.toContain("access_token");
    expect(cookies.map((c) => c.name)).not.toContain("refresh_token");
    const stored = await page.evaluate(() => ({
      access: localStorage.getItem("sd_access"),
      auth: localStorage.getItem("sd_auth"),
    }));
    expect(stored.access).toBeNull();
    // No user profile may be persisted by a failed login.
    if (stored.auth) {
      const parsed = JSON.parse(stored.auth) as { state?: { user?: unknown } };
      expect(parsed.state?.user ?? null).toBeNull();
    }
  });

  test("direct visit to an admin route as anonymous lands on /login, never admin content", async ({
    page,
  }) => {
    await page.goto(`${BASE}/admin/products`);
    await expect(page).toHaveURL(/\/login/);
    // The admin page must not have painted: no products table, no admin nav.
    await expect(page.locator("tbody tr")).toHaveCount(0);
  });
});
