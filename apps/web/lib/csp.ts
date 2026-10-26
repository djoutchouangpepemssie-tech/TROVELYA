import { sentryIngestOrigin } from "./sentry";

/** Scheme and host of a configured URL ("" when absent or invalid): never a path or a wildcard. */
function originOf(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

/** Content-Security-Policy with a fresh nonce per request (section 13.2): no inline scripts. */
export function contentSecurityPolicy(nonce: string, isDev: boolean): string {
  const sentryOrigin = sentryIngestOrigin(process.env.NEXT_PUBLIC_SENTRY_DSN);
  // Photos go straight from the browser to object storage and are shown from the public
  // variants bucket (ADR-0019); both hosts are server-side settings, never NEXT_PUBLIC_*.
  const uploadOrigin = originOf(process.env.MEDIA_UPLOAD_ORIGIN);
  const mediaOrigin = originOf(process.env.MEDIA_PUBLIC_URL);
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    ["img-src 'self' data: blob:", mediaOrigin].filter(Boolean).join(" "),
    "font-src 'self'",
    // The browser reaches the API through the same-origin relay /api/* (ADR-0015).
    ["connect-src 'self'", sentryOrigin, uploadOrigin].filter(Boolean).join(" "),
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ].join("; ");
}
