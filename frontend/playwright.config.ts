import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.PORT ?? "3000";
const MOCK_PORT = process.env.MOCK_PORT ?? "8000";
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `node e2e/mock-backend.mjs`,
      url: `http://127.0.0.1:${MOCK_PORT}/__mock/health`,
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
      env: { MOCK_PORT },
    },
    {
      command: "pnpm dev",
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        BUSCASAM_API_URL: `http://127.0.0.1:${MOCK_PORT}`,
        BUSCASAM_INTERNAL_API_URL: `http://127.0.0.1:${MOCK_PORT}/api`,
      },
    },
  ],
});
