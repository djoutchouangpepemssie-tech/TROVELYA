import { defineConfig, devices } from "@playwright/test";

// Journey 1 on the full stack (P1 gate, G1): API, worker and Mailpit in containers from
// tests/e2e-full/stack.sh, the production build of the web app in front, as served to users.
const PORT = Number(process.env.FULL_WEB_PORT ?? 3200);
const API_PORT = Number(process.env.FULL_API_PORT ?? 8200);
// The same test-only value as in tests/e2e-full/stack.sh, never a real secret.
const PROXY_SHARED_SECRET = "ci-only-secret-key-full-proxy-0123456789abcdef";

export default defineConfig({
  testDir: "./tests/e2e-full",
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? "github" : "list",
  timeout: 90_000,
  use: {
    baseURL: `http://localhost:${PORT}`,
    ...devices["Desktop Chrome"],
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : {},
  },
  webServer: {
    command: `pnpm start --port ${String(PORT)}`,
    url: `http://localhost:${String(PORT)}/fr`,
    env: { API_INTERNAL_URL: `http://127.0.0.1:${String(API_PORT)}`, PROXY_SHARED_SECRET },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
