/**
 * Typed TROVÉLYA API client (ADR-0004). Types are generated from docs/api/openapi.json:
 * run `pnpm api:generate` at the repository root after changing an API route.
 */
import createClient, { type Client, type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

export type { components, operations, paths } from "./schema";
export type ApiClient = Client<paths>;

const CSRF_COOKIE = "trv_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${name}=`;
  return document.cookie
    .split("; ")
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length);
}

/** Double-submit CSRF (section 11.1): echo the trv_csrf cookie on unsafe methods. */
const csrf: Middleware = {
  onRequest({ request }) {
    if (SAFE_METHODS.has(request.method)) return undefined;
    const token = readCookie(CSRF_COOKIE);
    if (token) request.headers.set(CSRF_HEADER, token);
    return request;
  },
};

export function createApiClient(baseUrl: string, init: { fetch?: typeof fetch } = {}): ApiClient {
  const client = createClient<paths>({
    baseUrl,
    credentials: "include",
    ...(init.fetch ? { fetch: init.fetch } : {}),
  });
  client.use(csrf);
  return client;
}
