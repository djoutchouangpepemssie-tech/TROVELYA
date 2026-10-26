import { afterEach, describe, expect, it, vi } from "vitest";

import { contentSecurityPolicy } from "./csp";

const connectSrc = (csp: string) => csp.split("; ").find((d) => d.startsWith("connect-src"));
const imgSrc = (csp: string) => csp.split("; ").find((d) => d.startsWith("img-src"));

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

  it("lets the browser upload to the storage host and show the variants (ADR-0019)", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    vi.stubEnv("MEDIA_UPLOAD_ORIGIN", "https://acc.eu.r2.cloudflarestorage.com");
    vi.stubEnv("MEDIA_PUBLIC_URL", "https://pub-123.r2.dev/some/path");
    const csp = contentSecurityPolicy("n", false);
    expect(connectSrc(csp)).toBe("connect-src 'self' https://acc.eu.r2.cloudflarestorage.com");
    expect(imgSrc(csp)).toBe("img-src 'self' data: blob: https://pub-123.r2.dev");
  });

  it("adds no media host when unset or invalid", () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    vi.stubEnv("MEDIA_UPLOAD_ORIGIN", "not a url");
    vi.stubEnv("MEDIA_PUBLIC_URL", "");
    const csp = contentSecurityPolicy("n", false);
    expect(connectSrc(csp)).toBe("connect-src 'self'");
    expect(imgSrc(csp)).toBe("img-src 'self' data: blob:");
  });
});
