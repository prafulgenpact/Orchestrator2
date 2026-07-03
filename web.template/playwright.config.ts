import { defineConfig } from "@playwright/test";

// Deterministic browser E2E: pinned browser via @playwright/test version,
// fixed viewport, no retries locally (a flaky test is a failing test),
// webServer boots YOUR real app so tests hit the assembled system.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["junit", { outputFile: "../reports/junit-web-e2e.xml" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    viewport: { width: 1280, height: 720 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
