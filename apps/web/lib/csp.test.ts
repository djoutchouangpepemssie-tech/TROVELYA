import { afterEach, describe, expect, it, vi } from "vitest";

import { contentSecurityPolicy } from "./csp";

const connectSrc = (csp: string) => csp.split("; ").find((d) => d.startsWith("connect-src"));

describe("contentSecurityPolicy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows the EU Sentry ingest host when a DSN is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.de.sentry.io/2");
    expect(connectSrc(contentSecurityPolicy("n", false))).toBe(
      "connect-src 'self' https://o1.ingest.de.sentry.io",
    );
  });

  it("never lists the API: the browser goes through the same-origin relay", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test");
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.test");
    expect(contentSecurityPolicy("n", false)).not.toContain("api.example.test");
  });

  it("allows only the site itself when nothing is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    expect(connectSrc(contentSecurityPolicy("n", false))).toBe("connect-src 'self'");
  });
});
