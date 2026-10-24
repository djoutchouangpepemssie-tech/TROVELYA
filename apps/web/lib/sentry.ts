/** Scheme and host of a Sentry DSN, for the CSP connect-src ("" when absent or invalid). */
export function sentryIngestOrigin(dsn: string | undefined): string {
  if (!dsn) return "";
  try {
    return new URL(dsn).origin;
  } catch {
    return "";
  }
}

/** Shared Sentry options (EU region: the DSN points to ingest.de.sentry.io). */
export function sentryOptions() {
  const environment = process.env.NEXT_PUBLIC_VERCEL_ENV ?? "development";
  return {
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    enabled: Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN),
    environment,
    // GDPR: no IP address, cookies or user identity are sent.
    sendDefaultPii: false,
    tracesSampleRate: environment === "production" ? 0.1 : 1.0,
  };
}
