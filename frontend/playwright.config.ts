import { defineConfig } from "@playwright/test";

// Browser tests (Phase 4): the real app on a fresh seeded database, driven in the Microsoft Edge
// installed on this machine. No browser is downloaded (owner approval, 2026-10-14).
const PORT = Number(process.env.MARGIN_E2E_PORT ?? "8765");

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${String(PORT)}`,
    ...(process.env.MARGIN_BROWSER_PATH ? {} : { channel: "msedge" }),
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
    launchOptions: {
      ...(process.env.MARGIN_BROWSER_PATH
        ? { executablePath: process.env.MARGIN_BROWSER_PATH }
        : {}),
      // Keep the browser from contacting anything other than the local app.
      args: [
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--no-first-run",
      ],
    },
  },
  webServer: {
    command: `uv run --frozen python ../scripts/e2e_server.py --port ${String(PORT)}`,
    cwd: "../backend",
    url: `http://127.0.0.1:${String(PORT)}/api/health`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: { UV_PYTHON_PREFERENCE: "only-managed" },
    stdout: "pipe",
  },
});
