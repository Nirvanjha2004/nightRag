import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the UI runs on 5173 and the API on 8000, so /api is proxied to
// keep every fetch same-origin (no CORS setup needed to get started).
// In production `npm run build` writes to web/dist, which the FastAPI app serves
// itself — same origin, same port, one command to run the whole thing.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.NIGHTRAG_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        // The three heavy dependencies change far less often than app code, so
        // they get their own chunks and stay cached across deploys.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          markdown: ["react-markdown", "remark-gfm"],
          syntax: ["highlight.js/lib/core", "highlight.js/lib/languages/python"],
        },
      },
    },
  },
});
