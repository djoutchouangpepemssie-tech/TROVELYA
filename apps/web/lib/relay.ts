/**
 * Same-origin relay to the API (ADR-0015).
 *
 * The browser only talks to the web origin, so the session cookie `__Host-trv_session` is a
 * first-party cookie even though the API lives on another site. The relay forwards an allow
 * list of headers and our own cookies, adds the visitor's IP and country as seen by Vercel
 * (Vercel overwrites `x-real-ip` and `x-forwarded-for`, so the browser cannot forge them) and
 * authenticates them with the shared secret the API checks.
 */

export type RelayConfig = { apiUrl: string; proxySecret: string };

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "content-type",
  "if-match",
  "idempotency-key",
  "x-csrf-token",
  "x-request-id",
];
const DROPPED_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "set-cookie",
]);
const OUR_COOKIE_PREFIX = "__Host-trv_";
const MAX_BODY_BYTES = 1_048_576;
const UPSTREAM_TIMEOUT_MS = 15_000;

function problem(status: number, code: string, title: string): Response {
  return Response.json(
    { type: `https://docs.trovelya.com/errors/${code}`, title, status, code },
    {
      status,
      headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
    },
  );
}

function ourCookies(header: string | null): string | null {
  if (!header) return null;
  const kept = header
    .split(";")
    .map((pair) => pair.trim())
    .filter((pair) => pair.startsWith(OUR_COOKIE_PREFIX));
  return kept.length > 0 ? kept.join("; ") : null;
}

function visitorIp(headers: Headers): string | null {
  const realIp = headers.get("x-real-ip");
  if (realIp) return realIp.trim();
  const first = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return first || null;
}

function upstreamHeaders(request: Request, config: RelayConfig): Headers {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  const cookies = ourCookies(request.headers.get("cookie"));
  if (cookies) headers.set("cookie", cookies);
  const ip = visitorIp(request.headers);
  if (ip) headers.set("x-trv-client-ip", ip);
  const country = request.headers.get("x-vercel-ip-country");
  if (country) headers.set("x-trv-client-country", country);
  headers.set("x-trv-proxy-secret", config.proxySecret);
  return headers;
}

function isApiPath(path: readonly string[]): boolean {
  return (
    path[0] === "v1" &&
    path.every((segment) => segment !== "" && segment !== "." && segment !== "..")
  );
}

async function readBody(request: Request): Promise<ArrayBuffer | null | "too_large"> {
  if (request.method === "GET" || request.method === "HEAD") return null;
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return "too_large";
  const body = await request.arrayBuffer();
  return body.byteLength > MAX_BODY_BYTES ? "too_large" : body;
}

function downstreamResponse(upstream: Response): Response {
  const headers = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!DROPPED_RESPONSE_HEADERS.has(name)) headers.set(name, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) headers.append("set-cookie", cookie);
  headers.set("cache-control", "no-store");
  return new Response(upstream.body, { status: upstream.status, headers });
}

export async function relay(
  request: Request,
  path: readonly string[],
  config: RelayConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (!config.apiUrl || !config.proxySecret) {
    return problem(503, "service_unavailable", "Service indisponible");
  }
  if (!isApiPath(path)) return problem(404, "not_found", "Ressource introuvable");

  const body = await readBody(request);
  if (body === "too_large") return problem(413, "payload_too_large", "Requête trop volumineuse");

  const search = new URL(request.url).search;
  const target = `${config.apiUrl.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}${search}`;
  try {
    const upstream = await fetchImpl(target, {
      method: request.method,
      headers: upstreamHeaders(request, config),
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    return downstreamResponse(upstream);
  } catch {
    return problem(502, "service_unavailable", "Service indisponible");
  }
}
