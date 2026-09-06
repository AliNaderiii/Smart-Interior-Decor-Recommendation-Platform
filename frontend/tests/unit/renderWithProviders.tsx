/** Shared render helper for component tests.
 *
 * Since the bilingual runtime landed (`src/i18n`), every page calls `useT()`
 * and therefore MUST be rendered inside `<LocaleProvider>` — otherwise React
 * throws "useLocale must be used inside <LocaleProvider>" before the code
 * under test even runs. That is exactly what broke `loginPage.test.tsx` in CI
 * from commit 459fbf4 onward.
 *
 * The provider reads the persisted locale from localStorage on mount and the
 * app default is Persian. The unit specs assert against the ENGLISH catalogue
 * (`/sign in/i`, "Login failed", …), so this helper pins `en` unless a test
 * explicitly asks for `fa`. Pinning happens BEFORE render, because
 * `LocaleProvider` samples localStorage in its `useState` initialiser.
 *
 * Tests that need routing/query/toast providers compose them as `wrapper`
 * children — see `designerQuotaToast.test.tsx`.
 */
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { LocaleProvider, type Locale } from "@/i18n";

export const LOCALE_STORAGE_KEY = "smartdecor.locale";

/** Persist a locale exactly the way the app does, so `LocaleProvider` picks
 *  it up on mount. Safe to call in `beforeEach` after `localStorage.clear()`. */
export function setTestLocale(locale: Locale): void {
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
}

type Options = Omit<RenderOptions, "wrapper"> & {
  /** Defaults to `en` — the language the existing assertions are written in. */
  locale?: Locale;
  /** Extra providers to nest INSIDE LocaleProvider (router, query client, …). */
  wrapper?: (props: { children: ReactNode }) => ReactElement;
};

export function renderWithProviders(ui: ReactElement, options: Options = {}): RenderResult {
  const { locale = "en", wrapper: Inner, ...rest } = options;
  setTestLocale(locale);

  function AllProviders({ children }: { children: ReactNode }) {
    return (
      <LocaleProvider>{Inner ? <Inner>{children}</Inner> : children}</LocaleProvider>
    );
  }

  return render(ui, { wrapper: AllProviders, ...rest });
}
