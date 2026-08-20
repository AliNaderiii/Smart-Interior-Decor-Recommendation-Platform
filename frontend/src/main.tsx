import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Self-hosted fonts (no external font CDN): Inter for Latin, Vazirmatn for
// Persian glyphs (prices, labels). RTL-ready per docs/DESIGN_SYSTEM.md.
// V2: only the subsets we actually render — see src/fonts.css.
import "./fonts.css";
import { useThemeStore, applyMode } from "@/stores/themeStore";

// Apply the persisted theme before first paint to avoid a light-mode flash.
applyMode(useThemeStore.getState().mode);
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
