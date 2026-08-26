/** Vitest setup (Stage 1, T-1.4).
 *
 * @testing-library/react's auto-cleanup only registers when a global
 * `afterEach` exists (test globals). This repo keeps explicit `vitest`
 * imports, so the cleanup hook is registered here manually — otherwise
 * renders accumulate in the shared jsdom document across tests in a file.
 */
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/** jsdom implements no CSS media queries, so `window.matchMedia` is simply
 *  absent — and anything that renders a page pulls in `themeStore`, which
 *  reads `prefers-color-scheme` at module load. Without this the suite fails
 *  at import time with "window.matchMedia is not a function", nowhere near
 *  the code under test. Reports "light" (no dark preference), which is the
 *  store's own fallback for non-browser environments. */
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
});
