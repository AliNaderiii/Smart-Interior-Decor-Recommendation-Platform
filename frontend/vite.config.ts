import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/media": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  preview: {
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/media": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    target: "es2020",
    rollupOptions: {
      output: {
        // NOTE: react-grid-layout is deliberately NOT named here.
        // Phase 0B found that naming it in manualChunks pulled it into the
        // static entry graph, so Vite emitted a <link rel="modulepreload">
        // for it in index.html — the React.lazy() boundary still deferred
        // execution, but ~21 KB gzip was fetched on 100% of routes.
        // Letting the dynamic import() create the chunk keeps it truly lazy.
        manualChunks(id: string) {
          // Must come first. These are reachable ONLY from the dynamic
          // import() in MoodboardEditorPage, but they also match the
          // "node_modules/react" test below — which would forcibly assign
          // them to the eager vendor chunk and undo the lazy loading.
          // Returning undefined leaves them in the async chunk Rollup
          // derives from the dynamic import.
          if (
            id.includes("react-grid-layout") ||
            id.includes("react-draggable") ||
            id.includes("react-resizable")
          ) {
            return undefined;
          }
          if (id.includes("@tanstack") || id.includes("zustand")) return "query";
          if (id.includes("node_modules/react") || id.includes("react-router")) return "vendor";
          return undefined;
        },
      },
    },
  },
});
