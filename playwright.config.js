const { defineConfig, devices } = require("@playwright/test");
const python = process.platform === "win32" ? ".\\.venv\\Scripts\\python.exe" : ".venv/bin/python";

module.exports = defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
    ["json", { outputFile: "test-results/playwright-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
    url: "http://127.0.0.1:8001/api/health",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { TASKS_DB_PATH: "data/taskboard-e2e.db" },
  },
});