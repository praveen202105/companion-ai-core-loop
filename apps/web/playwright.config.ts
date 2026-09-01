import { defineConfig, devices } from "@playwright/test";

const executablePath = process.env.PATH || "";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command:
        "uv run --package companion-ai-api uvicorn companion.api:app --host 127.0.0.1 --port 8100",
      cwd: "../..",
      url: "http://127.0.0.1:8100/health/ready",
      reuseExistingServer: !process.env.CI,
      env: {
        PATH: executablePath,
        PYTHONPATH: "apps/api/src",
        DATABASE_URL: "sqlite:///./tmp/e2e.db",
        INTERNAL_API_KEY: "e2e-internal-key",
        LLM_PROVIDER: "fake",
        EMBEDDING_PROVIDER: "hash",
      },
    },
    {
      command: "pnpm dev --port 3100",
      cwd: ".",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: !process.env.CI,
      env: {
        PATH: executablePath,
        API_BASE_URL: "http://127.0.0.1:8100",
        INTERNAL_API_KEY: "e2e-internal-key",
        DEMO_PASSCODE: "companion-demo",
        COOKIE_SIGNING_SECRET: "e2e-cookie-signing-secret-123456789",
      },
    },
  ],
});
