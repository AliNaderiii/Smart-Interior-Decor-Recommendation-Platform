/** Locale runtime: persisted language choice, direction, and the `useT` hook.
 *
 * Design notes
 * ------------
 * * Persian is the default (`fa`): the target market is Iranian — prices are in
 *   Toman and seller links point at Digikala.
 * * Direction is a *document* property, not a component one. Setting
 *   `dir`/`lang` on <html> lets every logical CSS property (`ms-`, `me-`,
 *   `text-start`) flip for free, which is why the codebase was migrated off
 *   physical `ml-`/`text-right` classes first.
 * * The choice is written to localStorage and applied before first paint (see
 *   `applyLocale` called from main.tsx) so the page never flashes the wrong
 *   direction.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { fa, type Dict } from "./fa";
import { en } from "./en";

export type Locale = "fa" | "en";

const STORAGE_KEY = "smartdecor.locale";
const CATALOGUES: Record<Locale, Dict> = { fa, en };

export function isRtl(locale: Locale): boolean {
  return locale === "fa";
}

/** Persisted choice, falling back to Persian. Never throws: private-mode
 *  Safari and some in-app browsers make localStorage access itself raise. */
export function readStoredLocale(): Locale {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "fa" || v === "en") return v;
  } catch {
    /* storage unavailable — fall through to the default */
  }
  return "fa";
}

/** Applies locale to the document. Safe to call before React mounts. */
export function applyLocale(locale: Locale): void {
  const el = document.documentElement;
  el.lang = locale;
  el.dir = isRtl(locale) ? "rtl" : "ltr";
  // Font stack follows the locale: Vazirmatn leads for Persian, Inter for
  // English. Persian text set in Inter falls back per-glyph and looks cramped.
  el.style.setProperty(
    "--font-sans",
    isRtl(locale)
      ? '"Vazirmatn", "Inter Variable", ui-sans-serif, system-ui, sans-serif'
      : '"Inter Variable", "Vazirmatn", ui-sans-serif, system-ui, sans-serif',
  );
}

type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: Dict;
  rtl: boolean;
  /** Digits follow the locale: Persian numerals in fa, Latin in en. */
  num: (v: number | string) => string;
  /** Toman amount, grouped, with locale-appropriate digits. */
  money: (v: number) => string;
};

const LocaleContext = createContext<Ctx | null>(null);

function toPersianDigits(input: number | string): string {
  return String(input).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  useEffect(() => {
    applyLocale(locale);
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* non-fatal: the choice simply will not survive a reload */
    }
  }, []);

  const rtl = isRtl(locale);
  const num = useCallback(
    (v: number | string) => {
      const grouped = new Intl.NumberFormat("en-US").format(
        typeof v === "number" ? v : Number(v),
      );
      const safe = Number.isNaN(Number(v)) ? String(v) : grouped;
      return rtl ? toPersianDigits(safe) : safe;
    },
    [rtl],
  );
  const money = useCallback((v: number) => num(v), [num]);

  return (
    <LocaleContext.Provider
      value={{ locale, setLocale, t: CATALOGUES[locale], rtl, num, money }}
    >
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): Ctx {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used inside <LocaleProvider>");
  return ctx;
}

/** Shorthand for the common case: `const t = useT();` */
export function useT(): Dict {
  return useLocale().t;
}

/** Picks the locale-appropriate field from a dataset row that ships both,
 *  e.g. `pick(product, "title")` -> `title_fa` in Persian, `title` in English.
 *  The catalogue JSON already carries `*_fa` / `*_en` pairs. */
export function pickField<T extends Record<string, unknown>>(
  row: T,
  base: string,
  locale: Locale,
): string {
  const faKey = `${base}_fa`;
  const enKey = `${base}_en`;
  const value = locale === "fa" ? row[faKey] ?? row[enKey] ?? row[base] : row[enKey] ?? row[base] ?? row[faKey];
  return typeof value === "string" ? value : "";
}
