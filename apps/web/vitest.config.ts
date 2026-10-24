import { defineConfig } from "vitest/config";

// Unit tests only: browser tests live in tests/e2e and run with Playwright.
export default defineConfig({
  // tsconfig keeps JSX for Next.js ("preserve"): compile it here for the tests.
  oxc: { jsx: { runtime: "automatic" } },
  test: { include: ["**/*.test.{ts,tsx}"], exclude: ["node_modules", ".next", "tests/e2e"] },
});
