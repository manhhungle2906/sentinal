import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const CORE_TARGET = process.env.CORE_TARGET ?? "http://localhost:8000";
const INGEST_TARGET = process.env.INGEST_TARGET ?? "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: CORE_TARGET, changeOrigin: true },
      "/ingest": { target: INGEST_TARGET, changeOrigin: true },
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
