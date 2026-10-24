import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const API_PORT = 8100;

// Test-only values, never real secrets (`.gitleaks.toml` allows the `ci-only-secret-key-` prefix).
const PROXY_SHARED_SECRET = "ci-only-secret-key-e2e-proxy-0123456789abcdef";
const API_ENV = {
  ENV: "test",
  DATABASE_URL: process.env.E2E_DATABASE_URL ?? "postgresql://postgres:e2e@localhost:5433/postgres",
  REDIS_URL: process.env.E2E_REDIS_URL ?? "redis://localhost:6380/0",
  SECRET_KEY: "ci-only-secret-key-e2e-session-0123456789abcdef0123456789abcdef0123456789",
  PROXY_SHARED_SECRET,
  FIELD_ENCRYPTION_KEY: "ci-only-secret-key-e2e-fields-0123456789abcdef",
  WEB_ORIGIN: `http://localhost:${PORT}`,
  ADMIN_ORIGIN: "http://localhost:3101",
  EMAIL_PROVIDER: "fake",
  GEOCODER_PROVIDER: "fake",
  FEATURE_FLAGS_DEFAULT: "{}",
};

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    ...devices["Desktop Chrome"],
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : {},
  },
  // The whole stack: the real API (database and Redis from tests/e2e/stack.sh) behind the
  // production build of the web app, as served to users.
  webServer: [
    {
      command: "bash tests/e2e/start-api.sh",
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { ...API_ENV, E2E_API_PORT: String(API_PORT) },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `pnpm start --port ${PORT}`,
      url: `http://localhost:${PORT}/fr`,
      env: { API_INTERNAL_URL: `http://127.0.0.1:${API_PORT}`, PROXY_SHARED_SECRET },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
