import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 8765);

// The suites run against the production build served by FastAPI (one origin, like the clinic LAN).
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `../.venv/bin/python ../scripts/e2e_server.py --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/system/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
  },
});
