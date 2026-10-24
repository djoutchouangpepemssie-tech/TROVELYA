import { afterEach, describe, expect, it, vi } from "vitest";

import { contentSecurityPolicy } from "./csp";

const connectSrc = (csp: string) => csp.split("; ").find((d) => d.startsWith("connect-src"));

describe("contentSecurityPolicy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows the EU Sentry ingest host when a DSN is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.de.sentry.io/2");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test");
    expect(connectSrc(contentSecurityPolicy("n", false))).toBe(
      "connect-src 'self' https://api.example.test https://o1.ingest.de.sentry.io",
    );
  });

  it("allows only the site itself when nothing is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(connectSrc(contentSecurityPolicy("n", false))).toBe("connect-src 'self'");
  });
});
