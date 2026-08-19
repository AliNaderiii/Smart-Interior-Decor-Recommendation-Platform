import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Self-hosted fonts (no external font CDN): Inter for Latin, Vazirmatn for
// Persian glyphs (prices, labels). RTL-ready per docs/DESIGN_SYSTEM.md.
import "@fontsource-variable/inter/index.css";
import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/700.css";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
