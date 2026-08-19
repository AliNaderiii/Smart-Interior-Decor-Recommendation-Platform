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
        // Keep the heavy drag&drop lib out of the recommendation page bundle (LCP)
        manualChunks(id: string) {
          if (id.includes("react-grid-layout")) return "gridlayout";
          if (id.includes("@tanstack") || id.includes("axios") || id.includes("zustand")) return "query";
          if (id.includes("node_modules/react") || id.includes("react-router")) return "vendor";
          return undefined;
        },
      },
    },
  },
});
