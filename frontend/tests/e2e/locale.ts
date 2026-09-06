/**
 * E2E locale pinning — the one place that decides which language the
 * browser-driven suite runs in.
 *
 * WHY THIS MODULE EXISTS (CI red from commit 459fbf4, "Persian UI, RTL")
 * ----------------------------------------------------------------------
 * The app became bilingual with Persian as the DEFAULT. Every spec in this
 * directory was written against the English copy (`getByLabel(/email/i)`,
 * `getByRole("button", { name: /sign in/i })`, `/room width/i`, …), so the
 * moment the default flipped, `globalSetup` could no longer find the login
 * form and all four role projects went down with it.
 *
 * The locale is persisted by the app in `localStorage["smartdecor.locale"]`
 * and read BEFORE React mounts (`main.tsx` → `readStoredLocale()`), so the
 * correct fix is to have that key present before the first script of every
 * page runs. Two mechanisms cover every context the suite creates:
 *
 *   1. `addInitScript` on the contexts globalSetup logs in with — the value
 *      is then captured into each role's storageState and inherited by the
 *      role projects for free.
 *   2. A minimal storageState file for the anonymous projects (`chromium`,
 *      `chromium-sweep`), which never go through globalSetup's login.
 *
 * Switch languages with `E2E_LOCALE=fa` once the selectors that still depend
 * on English copy have been migrated to `data-testid` / role-only queries
 * (the login form already has: see `LoginPage.tsx`).
 */
import fs from "node:fs";

/** Must match `STORAGE_KEY` in `src/i18n/index.tsx`. */
export const LOCALE_STORAGE_KEY = "smartdecor.locale";

export type E2ELocale = "en" | "fa";

function parseLocale(raw: string | undefined): E2ELocale {
  if (raw === "fa" || raw === "en") return raw;
  if (raw !== undefined && raw !== "") {
    console.warn(`E2E_LOCALE="${raw}" is not "en" | "fa" — falling back to "en".`);
  }
  return "en";
}

/** Language the suite runs in. Defaults to English (what the specs assert). */
export const E2E_LOCALE: E2ELocale = parseLocale(process.env.E2E_LOCALE);

/**
 * Init script for `context.addInitScript` / `page.addInitScript`: seeds the
 * locale before any application code runs, on every navigation. Wrapped in
 * try/catch because the app itself tolerates an unavailable localStorage.
 */
export function localeInitScript(locale: E2ELocale = E2E_LOCALE): string {
  return `try { localStorage.setItem(${JSON.stringify(LOCALE_STORAGE_KEY)}, ${JSON.stringify(locale)}); } catch {}`;
}

/**
 * Write a storageState file that contains ONLY the locale entry for `origin`.
 * Used for the anonymous projects so they open the app in the same language
 * as the authenticated ones. Returns the path it wrote for logging.
 */
export function writeAnonymousStorageState(
  filePath: string,
  origin: string,
  locale: E2ELocale = E2E_LOCALE,
): string {
  const state = {
    cookies: [],
    origins: [
      {
        origin,
        localStorage: [{ name: LOCALE_STORAGE_KEY, value: locale }],
      },
    ],
  };
  fs.writeFileSync(filePath, JSON.stringify(state, null, 2));
  return filePath;
}
