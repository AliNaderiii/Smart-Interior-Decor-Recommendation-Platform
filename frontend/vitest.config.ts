import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Unit-test runner (Stage 1, T-1.3).
 *
 * `npm test` -> `vitest run` (single pass, CI-friendly). The Playwright suite
 * is separate (`npm run e2e`, tests/e2e) — Vitest never touches a browser.
 *
 * jsdom provides window/localStorage/document for the stores and URL
 * sanitiser; the Tailwind plugin is deliberately NOT loaded here — the
 * tests assert behaviour, not CSS.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    setupFiles: ["./tests/unit/setup.ts"],
    reporters: ["default"],
  },
});
