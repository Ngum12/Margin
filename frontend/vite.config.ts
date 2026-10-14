/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendUrl = process.env.MARGIN_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    // Inline nothing from remote origins; every asset is emitted locally.
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      "/api": backendUrl,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    testTimeout: 15000,
  },
});
