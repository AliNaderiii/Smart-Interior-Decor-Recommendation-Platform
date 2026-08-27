/**
 * Homeowner end-to-end journey (Stage 1, T-1.4 close-out).
 *
 * Contractual scope covered (client advertisement, Portal 1):
 *   style quiz (5 steps) -> 3-5 ranked products per category with an
 *   explanation chip -> editable moodboard -> shopping list with price and a
 *   live total -> logout.
 *
 * Runs in the `chromium-homeowner` project, whose session comes from the
 * storageState written by globalSetup.ts (a real UI login as
 * demo@smartdecor.dev).
 *
 * Selector policy: roles and accessible names only (the same policy as
 * auth-smoke.spec.ts). No CSS-class or nth-child selectors — those break on
 * every restyle and would make this suite the flakiest thing in CI.
 *
 * Ordering: the tests in this file are sequential and share server state (a
 * moodboard created in one test is read by the next), so the file runs
 * serially. `workers: 1` + `fullyParallel: false` in playwright.config.ts
 * already guarantee that; `test.describe.serial` makes it explicit and stops
 * later steps from running against a half-built fixture after a failure.
 */
import { test, expect, type Page } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** Unique per run so re-runs never collide on a board title. */
const BOARD_TITLE = `E2E Board ${Date.now()}`;

/** Persian digits, as produced by Intl.NumberFormat("fa-IR") in
 *  `formatToman`. A price rendered by the app looks like «۴۵٬۰۰۰٬۰۰۰ تومان». */
const TOMAN_PRICE = /[۰-۹0-9][۰-۹0-9٬,\s]*\s*تومان/;

/** Walk the 5-step quiz and submit it. Leaves the page on
 *  /recommendations?quiz=<id>. */
/** Wait until the stepper reports the given 0-based step as current.
 *
 *  QuizPage renders `<li aria-current="step">` for the active segment, so this
 *  is the app's own statement about which step is mounted. Without it the
 *  helper could interact with a step that React has not swapped in yet: the
 *  five steps share the same `button[aria-pressed]` tile markup, so a click
 *  can land on the OUTGOING step, leaving the incoming step with nothing
 *  selected and `Next` disabled — which is how this journey flaked in CI run
 *  33005106968 (`toBeEnabled` failed, 24x "unexpected value disabled"). */
async function waitForStep(page: Page, index: number) {
  const stepper = page.locator('ol[aria-label*="Quiz progress"]');
  try {
    await expect(stepper.nth(0).locator("li").nth(index)).toHaveAttribute(
      "aria-current",
      "step",
      { timeout: 20_000 },
    );
  } catch (error) {
    // Without this the whole test just burns its 120s budget and reports
    // "Received: undefined" against whatever assertion happened to be pending,
    // which says nothing about where it actually got stuck.
    const label = await stepper.first().getAttribute("aria-label").catch(() => null);
    const heading = await page.locator("main h1, h1").first().textContent().catch(() => null);
    throw new Error(
      `completeQuiz: the quiz never reached step ${index + 1}/5.\n` +
        `  url            : ${page.url()}\n` +
        `  stepper says   : ${label ?? "(no stepper found)"}\n` +
        `  page heading   : ${heading?.trim() ?? "(none)"}\n` +
        `  original error : ${error instanceof Error ? error.message.split("\n")[0] : String(error)}`,
    );
  }
}

/** Select the first tile of the current step and confirm the store took it.
 *
 *  IMPORTANT — the locator is scoped to `<main>`. `button[aria-pressed]` is
 *  NOT unique to the quiz: the header's dark-mode toggle
 *  (Layout.tsx:62, inside `<header>`) also carries aria-pressed and precedes
 *  the quiz tiles in DOM order. An unscoped `.first()` therefore clicked the
 *  THEME TOGGLE, flipped its aria-pressed to "true" — so the assertion below
 *  passed — while no style was ever selected, leaving `Next` disabled. That is
 *  the real cause of the "24 x unexpected value disabled" failures in runs
 *  33005106968 and 33008122154, and it is a selector bug, not shared state. */
async function pickFirstTile(page: Page) {
  const tile = page.locator("main button[aria-pressed]").first();
  await expect(tile).toBeVisible({ timeout: 20_000 });
  await tile.click();
  // The button is the source of truth: aria-pressed flips only once the store
  // has the answer, which is exactly the precondition for `Next` enabling.
  await expect(tile).toHaveAttribute("aria-pressed", "true", { timeout: 10_000 });
}

async function completeQuiz(page: Page) {
  await page.goto(`${BASE}/quiz`);
  await expect(page).toHaveURL(/\/quiz/);

  const next = page.getByRole("button", { name: /next/i });

  // Step 1 — style. Each style tile is a button with aria-pressed.
  await waitForStep(page, 0);
  await pickFirstTile(page);
  await expect(next).toBeEnabled();
  await next.click();

  // Step 2 — colour palette (same aria-pressed button pattern).
  await waitForStep(page, 1);
  await pickFirstTile(page);
  await expect(next).toBeEnabled();
  await next.click();

  // Step 3 — room dimensions. Defaults are already valid; set them explicitly
  // so the journey does not depend on the store's initial values.
  await waitForStep(page, 2);
  await page.getByLabel(/room width/i).fill("400", { timeout: 15_000 });
  await page.getByLabel(/room length/i).fill("500", { timeout: 15_000 });
  await expect(next).toBeEnabled();
  await next.click();

  // Step 4 — budget. The preset range buttons are the resilient control (the
  // histogram is a custom drag surface). Any preset gives max > min.
  await waitForStep(page, 3);
  await page.locator("main").getByRole("button", { name: /تومان|میلیون/ }).first().click().catch(() => {
    /* presets are dataset-driven; the store default is already a valid range */
  });
  await expect(next).toBeEnabled();
  await next.click();

  // Step 5 — materials (optional). Submit.
  await waitForStep(page, 4);
  const submit = page.getByRole("button", { name: /get my recommendations/i });
  await expect(submit).toBeVisible();
  await submit.click();

  await page.waitForURL(/\/recommendations/, { timeout: 60_000 });
}

test.describe.serial("homeowner journey", () => {
  test("completes the 5-step quiz and lands on recommendations", async ({ page }) => {
    await completeQuiz(page);
    await expect(page.getByRole("heading", { name: /your recommendations/i })).toBeVisible({
      timeout: 30_000,
    });
    // Never the login wall — this session is valid (cookie mode).
    await expect(page.locator("h1", { hasText: /welcome back/i })).toHaveCount(0);
  });

  test("every category returns 3-5 ranked items, each with an explanation chip", async ({
    page,
  }) => {
    await page.goto(`${BASE}/recommendations`);
    await expect(page.getByRole("heading", { name: /your recommendations/i })).toBeVisible({
      timeout: 60_000,
    });

    // Each category renders as a <section data-cat="..."> (RecommendationsPage).
    const sections = page.locator("section[data-cat]");
    const sectionCount = await sections.count();
    expect(sectionCount).toBeGreaterThan(0);

    for (let i = 0; i < sectionCount; i++) {
      const section = sections.nth(i);
      const category = await section.getAttribute("data-cat");

      // The "N options" counter is the page's own claim about the set size.
      // Assert the DOM instead: every card carries a "NN% match — why?"
      // explanation chip (locked/paywalled cards carry an Unlock CTA), so
      // counting chips + locked cards counts cards.
      const explanationChips = section.getByRole("button", { name: /why we matched/i });
      const lockedCards = section.getByRole("link", { name: /unlock with pro/i });
      const cards = (await explanationChips.count()) + (await lockedCards.count());

      // Contract: 3-5 ranked products per category.
      expect(
        cards,
        `category "${category}" returned ${cards} cards, expected 3-5`,
      ).toBeGreaterThanOrEqual(3);
      expect(
        cards,
        `category "${category}" returned ${cards} cards, expected 3-5`,
      ).toBeLessThanOrEqual(5);

      // Explanation chips are the "why did I get this" contract. At least one
      // unlocked card per category must expose one.
      expect(
        await explanationChips.count(),
        `category "${category}" has no explanation chip`,
      ).toBeGreaterThan(0);
    }
  });

  test("the explanation chip opens a match breakdown", async ({ page }) => {
    await page.goto(`${BASE}/recommendations`);
    const chip = page.getByRole("button", { name: /why we matched/i }).first();
    await expect(chip).toBeVisible({ timeout: 60_000 });
    await chip.click();
    // Radix HoverCard content: the per-signal breakdown the engine promises.
    await expect(page.getByText(/match breakdown/i)).toBeVisible();
    for (const signal of [/^Style$/, /^Colour$/, /^Budget$/, /^Material$/]) {
      await expect(page.getByText(signal).first()).toBeVisible();
    }
  });

  test("adds a product to a moodboard and the editor shows it", async ({ page }) => {
    await page.goto(`${BASE}/recommendations`);
    const addButton = page.getByRole("button", { name: /^add to moodboard$/i }).first();
    await expect(addButton).toBeVisible({ timeout: 60_000 });
    await addButton.click();
    // The button flips to its "already picked" state.
    await expect(page.getByRole("button", { name: /added/i }).first()).toBeVisible();

    // The header CTA counts the picks and navigates to /moodboards.
    const createCta = page.getByRole("button", { name: /create moodboard \(\d+\)/i });
    await expect(createCta).toBeEnabled();
    await createCta.click();
    await page.waitForURL(/\/moodboards/);

    // Name the board and create it; MoodboardsPage navigates to the editor.
    await page.getByLabel(/moodboard title/i).fill(BOARD_TITLE);
    await page.getByRole("button", { name: /^create moodboard$/i }).click();

    await page.waitForURL(/\/moodboard\/[0-9a-f-]+/i, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: BOARD_TITLE })).toBeVisible();
    // The board is not empty — the picked product made it onto the canvas.
    await expect(page.getByText(/this board is empty/i)).toHaveCount(0);
    await expect(page.getByText(/^\d+ items?$/).first()).toBeVisible();
  });

  test("the shopping list shows the item with a price and a total", async ({ page }) => {
    // Push the board's products onto the shopping list from the editor.
    await page.goto(`${BASE}/moodboards`);
    await expect(page.getByRole("heading", { name: BOARD_TITLE })).toBeVisible({
      timeout: 30_000,
    });
    await page
      .getByRole("heading", { name: BOARD_TITLE })
      .locator("xpath=ancestor::*[self::div][1]")
      .getByRole("link", { name: /^open$/i })
      .click();
    await page.waitForURL(/\/moodboard\/[0-9a-f-]+/i);

    await page.getByRole("button", { name: /add all to shopping list/i }).click();

    await page.goto(`${BASE}/shopping-list`);
    await expect(page.getByRole("heading", { name: /shopping list/i })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/nothing added yet|create a moodboard first/i)).toHaveCount(0);

    // At least one line item, each with a Toman price.
    const rows = page.locator("ul > li");
    await expect(rows.first()).toBeVisible();
    await expect(rows.first().getByText(TOMAN_PRICE).first()).toBeVisible();

    // The sticky total exists and is a Toman figure.
    const totalLabel = page.getByText(/^Total$/);
    await expect(totalLabel).toBeVisible();
    const totalValue = totalLabel.locator("xpath=following-sibling::p[1]");
    await expect(totalValue).toHaveText(TOMAN_PRICE);
    const before = (await totalValue.textContent())?.trim();

    // Increasing a quantity must move the total — a list whose total ignores
    // the stepper is worse than no total.
    await page.getByRole("button", { name: /increase quantity of/i }).first().click();
    await expect(totalValue).not.toHaveText(before ?? "", { timeout: 10_000 });
  });

  test("logout returns the browser to a logged-out state", async ({ page }) => {
    await page.goto(`${BASE}/`);
    await page.getByRole("button", { name: /log out/i }).click();
    await page.waitForURL(/\/login/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();

    // The session is really gone: an auth-gated route bounces back to /login.
    await page.goto(`${BASE}/moodboards`);
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });

    // And no auth cookies survive.
    const cookies = await page.context().cookies();
    const authCookies = cookies.filter((c) =>
      ["access_token", "refresh_token"].includes(c.name),
    );
    expect(
      authCookies.filter((c) => c.value !== ""),
      "auth cookies survived logout",
    ).toHaveLength(0);
  });
});
