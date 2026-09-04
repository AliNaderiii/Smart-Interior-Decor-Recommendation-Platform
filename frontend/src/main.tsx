import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// T-2.1: on /recommendations this fires the POST /recommend and preloads the
// LCP product photo BEFORE React boots — see src/lib/earlyRecommend.ts.
import "@/lib/earlyRecommend";
// Self-hosted fonts (no external font CDN): Inter for Latin, Vazirmatn for
// Persian glyphs (prices, labels). RTL-ready per docs/DESIGN_SYSTEM.md.
// V2: only the subsets we actually render — see src/fonts.css.
import "./fonts.css";
import { useThemeStore, applyMode } from "@/stores/themeStore";
import { applyLocale, readStoredLocale } from "@/i18n";

// Apply the persisted theme before first paint to avoid a light-mode flash.
applyMode(useThemeStore.getState().mode);
// Same reasoning for direction: setting lang/dir after mount makes the whole
// layout visibly jump from RTL to LTR on first paint.
applyLocale(readStoredLocale());
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
