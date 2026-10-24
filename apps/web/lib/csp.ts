import { sentryIngestOrigin } from "./sentry";

/** Content-Security-Policy with a fresh nonce per request (section 13.2): no inline scripts. */
export function contentSecurityPolicy(nonce: string, isDev: boolean): string {
  const sentryOrigin = sentryIngestOrigin(process.env.NEXT_PUBLIC_SENTRY_DSN);
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    // The browser reaches the API through the same-origin relay /api/* (ADR-0015).
    ["connect-src 'self'", sentryOrigin].filter(Boolean).join(" "),
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ].join("; ");
}
