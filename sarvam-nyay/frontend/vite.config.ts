import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Manual chunking — split the heavy "cool" libraries into their own
    // bundles so the initial JS download stays lean. Recharts and
    // Framer Motion together are ~150 KB gzipped; isolating them means
    // first-paint doesn't pay for features only the case-detail and
    // dashboard pages actually use.
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React + Router — every route needs this.
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          // Data layer — TanStack Query + Axios + Zustand.
          "vendor-data": [
            "@tanstack/react-query",
            "axios",
            "zustand",
          ],
          // Charts — only used by Dashboard + Case header.
          "vendor-charts": ["recharts"],
          // Motion — used on most pages but bundles cleanly.
          "vendor-motion": ["framer-motion"],
          // Command palette + forms + utilities.
          "vendor-ui": [
            "cmdk",
            "react-hook-form",
            "zod",
            "@hookform/resolvers",
            "lucide-react",
            "clsx",
            "date-fns",
            "react-hot-toast",
          ],
        },
      },
    },
    // Bump the warning ceiling so the rollup `(!) chunk > 500 kB` noise
    // only fires when a chunk is genuinely off the rails.
    chunkSizeWarningLimit: 600,
  },
});
