/**
 * Admin end-to-end journey (Stage 1, T-1.4 close-out).
 *
 * Contractual scope covered (client advertisement, Portal 3):
 *   product upload with image -> AI feature extraction (AI_PROVIDER=mock in
 *   CI) -> extraction preview -> manual review & approve (human-in-the-loop)
 *   -> the product appears in the VERIFIED list -> user management and
 *   subscription management pages load.
 *
 * Runs in the `chromium-admin` project (storageState from globalSetup,
 * admin@smartdecor.dev).
 *
 * The uploaded image is generated in-process (a tiny valid PNG) rather than
 * committed as a fixture binary: the backend sniffs magic bytes and
 * re-encodes (app/core/uploads.py), so a real PNG header is required, but the
 * pixels are irrelevant to the mock extractor.
 */
import { test, expect } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** A minimal but genuinely valid 1x1 PNG (IHDR + IDAT + IEND), so the
 *  backend's magic-byte validation and Pillow re-encode both succeed. */
const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test.describe.serial("admin journey", () => {
  test("the products console loads for an admin session", async ({ page }) => {
    await page.goto(`${BASE}/admin/products`);
    await expect(page).toHaveURL(/\/admin\/products/);
    await expect(page.getByRole("heading", { name: /^products$/i })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);

    // The catalogue really rendered rows (the DB is seeded with 100 products).
    await expect(page.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
  });

  test("uploading an image runs AI extraction and shows the preview", async ({ page }) => {
    await page.goto(`${BASE}/admin/products`);
    await expect(page.getByRole("heading", { name: /^products$/i })).toBeVisible({
      timeout: 30_000,
    });

    const uploadResponse = page.waitForResponse(
      (r) => r.url().includes("/api/v1/products/upload") && r.request().method() === "POST",
      { timeout: 60_000 },
    );

    // The file input is visually hidden but labelled; setInputFiles does not
    // need it to be visible.
    await page
      .getByLabel(/choose a product image to upload/i)
      .setInputFiles({ name: "e2e-product.png", mimeType: "image/png", buffer: PNG_1X1 });

    const response = await uploadResponse;
    expect(response.status(), "upload should create a draft product").toBe(201);
    // Envelope: { success, data: { product, extraction }, error }
    // (app/api/routes/products.py::upload_product_image).
    const body = (await response.json()) as {
      success: boolean;
      data: { product: { id: string; is_verified: boolean }; extraction: Record<string, unknown> };
    };
    expect(body.success).toBe(true);
    expect(body.data.product.id).toBeTruthy();
    // Human-in-the-loop: an upload is never auto-published.
    expect(body.data.product.is_verified).toBe(false);

    // AI feature extraction is the contractual bullet: colour, style and
    // material must all come back from the extractor, with a confidence.
    for (const field of ["colors", "style", "material", "confidence"]) {
      expect(body.data.extraction, `extraction is missing "${field}"`).toHaveProperty(field);
    }

    // The reviewer sees the extraction preview, with the confidence score.
    await expect(page.getByText(/ai extraction complete \(confidence \d+%\)/i)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("human-in-the-loop: a pending product can be reviewed and approved", async ({ page }) => {
    await page.goto(`${BASE}/admin/products`);
    await expect(page.getByRole("heading", { name: /^products$/i })).toBeVisible({
      timeout: 30_000,
    });

    // Filter to what is awaiting human review — the upload above landed here.
    await page.getByRole("button", { name: /^pending$/i }).click();
    const pendingRow = page.locator("tbody tr").first();
    await expect(pendingRow).toBeVisible({ timeout: 30_000 });
    await expect(pendingRow.getByText(/pending review/i)).toBeVisible();

    // The review surface: the JSON editor with the diff-vs-AI panel.
    await pendingRow.getByRole("button", { name: /^edit$/i }).click();
    const reviewDialog = page.getByRole("dialog", { name: /edit product/i });
    await expect(reviewDialog).toBeVisible();
    await expect(reviewDialog.getByText(/review ai extraction/i)).toBeVisible();
    await expect(reviewDialog.getByLabel(/product json/i)).toBeVisible();
    await expect(reviewDialog.getByText(/changes vs ai extraction/i)).toBeVisible();
    await reviewDialog.getByRole("button", { name: /^cancel$/i }).click();
    await expect(reviewDialog).toHaveCount(0);

    // Approve it. The verify call is the human-in-the-loop gate.
    const verifyResponse = page.waitForResponse(
      (r) => /\/api\/v1\/products\/[^/]+\/verify/.test(r.url()) && r.request().method() === "POST",
      { timeout: 30_000 },
    );
    await page.locator("tbody tr").first().getByRole("button", { name: /^verify$/i }).click();
    expect((await verifyResponse).status()).toBeLessThan(300);

    // It now shows up under "verified" and no longer as pending.
    await page.getByRole("button", { name: /^verified$/i }).click();
    const verifiedRow = page.locator("tbody tr").first();
    await expect(verifiedRow).toBeVisible({ timeout: 30_000 });
    await expect(verifiedRow.getByText(/^verified$/i)).toBeVisible();
  });

  test("style taxonomy is available to the reviewer", async ({ page }) => {
    await page.goto(`${BASE}/admin/products`);
    await expect(page.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
    await page.locator("tbody tr").first().getByRole("button", { name: /^edit$/i }).click();
    const reviewDialog = page.getByRole("dialog", { name: /edit product/i });
    await expect(reviewDialog.getByRole("group", { name: /style taxonomy/i })).toBeVisible();
    // The taxonomy chips are toggleable (assigning a style to a product).
    const chips = reviewDialog.getByRole("group", { name: /style taxonomy/i }).locator("button");
    expect(await chips.count()).toBeGreaterThan(0);
    await reviewDialog.getByRole("button", { name: /^cancel$/i }).click();
  });

  test("user management loads", async ({ page }) => {
    await page.goto(`${BASE}/admin/users`);
    await expect(page).toHaveURL(/\/admin\/users/);
    await expect(page.getByRole("heading", { name: /^users$/i })).toBeVisible({
      timeout: 30_000,
    });
    // The seeded demo accounts are listed.
    await expect(page.getByText("demo@smartdecor.dev").first()).toBeVisible({ timeout: 30_000 });
  });

  test("subscription management loads", async ({ page }) => {
    await page.goto(`${BASE}/admin/subscriptions`);
    await expect(page).toHaveURL(/\/admin\/subscriptions/);
    await expect(page.getByRole("heading", { name: /subscriptions/i })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);
  });
});
