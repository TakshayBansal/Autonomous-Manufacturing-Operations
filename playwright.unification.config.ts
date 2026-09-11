import { defineConfig, devices } from "@playwright/test";

// Contract-mocked UI checks: deliberately independent of demo seed quality.
// Real source-to-recovery acceptance remains in the full E2E suite.
export default defineConfig({
  testDir: "./apps/web/e2e",
  testMatch: "unification-contract.spec.ts",
  outputDir: "/tmp/genuinegigs-unification-browser-results",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3100", ...devices["Desktop Chrome"] },
  webServer: {
    command: "npm --workspace apps/web run start -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100/login",
    timeout: 60000,
    reuseExistingServer: false,
  },
});
