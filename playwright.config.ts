import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./apps/web/e2e",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: [
    { command: "python3 app.py", cwd: "services/factory-simulator", url: "http://127.0.0.1:8090/health", reuseExistingServer: !process.env.CI, timeout: 120_000, env: { FACTORY_SIMULATOR_TICK_SECONDS: "0.5" } },
    { command: ".venv/bin/python -m app.e2e_server", cwd: "apps/api", url: "http://127.0.0.1:8000/health/live", reuseExistingServer: !process.env.CI, timeout: 120_000 },
    { command: "npm run dev -- --hostname 127.0.0.1", cwd: "apps/web", url: "http://127.0.0.1:3000", reuseExistingServer: !process.env.CI, timeout: 120_000 },
  ],
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "tablet", use: { ...devices["iPad Pro 11"], browserName: "chromium" } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
