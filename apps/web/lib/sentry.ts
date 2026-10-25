/** Scheme and host of a Sentry DSN, for the CSP connect-src ("" when absent or invalid). */
export function sentryIngestOrigin(dsn: string | undefined): string {
  if (!dsn) return "";
  try {
    return new URL(dsn).origin;
  } catch {
    return "";
  }
}

// Sign-in and staff enrolment links carry a live token (#token=… or ?token=…).
const TOKEN = /(token=)[^&#\s"'\\]+/gi;

/** Removes the tokens from anything sent to Sentry (URLs in breadcrumbs, events, traces). */
export function scrubSecrets<T>(value: T): T | null {
  let text: string;
  try {
    text = JSON.stringify(value);
  } catch {
    return null; // Not serialisable, so not checkable: Sentry drops what is null.
  }
  const scrubbed = text.replace(TOKEN, "$1[filtré]");
  return scrubbed === text ? value : (JSON.parse(scrubbed) as T);
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
    beforeBreadcrumb: <T>(breadcrumb: T): T | null => scrubSecrets(breadcrumb),
    beforeSend: <T>(event: T): T | null => scrubSecrets(event),
    beforeSendTransaction: <T>(event: T): T | null => scrubSecrets(event),
  };
}
