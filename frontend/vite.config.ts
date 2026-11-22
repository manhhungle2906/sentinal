import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const CORE_TARGET = process.env.CORE_TARGET ?? "http://localhost:8000";
const INGEST_TARGET = process.env.INGEST_TARGET ?? "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Keep the browser Host header. changeOrigin rewrites it to the
      // upstream host, so the Core same-origin check rejects assignment and
      // every other state-changing request as cross-origin.
      "/api": { target: CORE_TARGET, changeOrigin: false },
      "/ingest": { target: INGEST_TARGET, changeOrigin: false },
    },
  },
  preview: {
    port: 4173,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
