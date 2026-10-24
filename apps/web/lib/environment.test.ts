import { describe, expect, it } from "vitest";

import { isProduction } from "./environment";

describe("isProduction", () => {
  it("is true on the Vercel production deployment", () => {
    expect(isProduction({ VERCEL_ENV: "production" })).toBe(true);
  });

  it("is true when APP_ENV says production", () => {
    expect(isProduction({ APP_ENV: "production" })).toBe(true);
  });

  it("is false for previews, staging and local runs", () => {
    expect(isProduction({ VERCEL_ENV: "preview" })).toBe(false);
    expect(isProduction({ APP_ENV: "staging" })).toBe(false);
    expect(isProduction({})).toBe(false);
  });
});
