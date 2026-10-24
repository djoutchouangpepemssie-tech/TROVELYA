import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";

import { routing } from "./i18n/routing";
import { contentSecurityPolicy } from "./lib/csp";

const handleI18n = createMiddleware(routing);

export function proxy(request: NextRequest): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  // Next.js reads the nonce from the request's CSP header and applies it to its own scripts.
  request.headers.set("x-nonce", nonce);
  request.headers.set("Content-Security-Policy", csp);
  const response = handleI18n(request);
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Everything except API routes, Next internals and static files (anything with a dot).
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
