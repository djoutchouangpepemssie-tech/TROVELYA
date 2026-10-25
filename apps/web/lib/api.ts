/**
 * Browser client for the API, through the same-origin relay `/api/*` (ADR-0015).
 *
 * Unsafe requests echo the signed CSRF cookie in `X-CSRF-Token` (double submit, 11.1); the
 * token is fetched first when the page does not have one yet.
 */

export const CSRF_COOKIE = "__Host-trv_csrf";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

type Dependencies = {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  cookies: () => string;
};

const browser: Dependencies = {
  fetch: (url, init) => fetch(url, init),
  cookies: () => document.cookie,
};

export function readCookie(name: string, cookies: string): string | null {
  for (const pair of cookies.split(";")) {
    const [key, ...value] = pair.trim().split("=");
    if (key === name) return value.join("=");
  }
  return null;
}

async function csrfToken(deps: Dependencies): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE, deps.cookies());
  if (existing) return existing;
  await deps.fetch("/api/v1/csrf", { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE, deps.cookies());
}

/** Fetch the CSRF token ahead, so a request sent while the page closes needs no extra call. */
export async function prepareCsrf(deps: Dependencies = browser): Promise<void> {
  await csrfToken(deps);
}

export async function apiFetch(
  path: `/v1/${string}`,
  init: RequestInit = {},
  deps: Dependencies = browser,
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (UNSAFE_METHODS.has(method)) {
    const token = await csrfToken(deps);
    if (token) headers.set("x-csrf-token", token);
  }
  return deps.fetch(`/api${path}`, { ...init, method, headers, credentials: "same-origin" });
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; code: string };

/** JSON call: the parsed body, or the status and error `code` (`network` when unreachable). */
export async function apiCall<T>(
  path: `/v1/${string}`,
  init: RequestInit = {},
  deps: Dependencies = browser,
): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("content-type", "application/json");
  let response: Response;
  try {
    response = await apiFetch(path, { ...init, headers }, deps);
  } catch {
    return { ok: false, status: 0, code: "network" };
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string };
    return { ok: false, status: response.status, code: body.code ?? "unknown" };
  }
  if (response.status === 204) {
    await response.body?.cancel();
    return { ok: true, data: null as T };
  }
  return { ok: true, data: (await response.json()) as T };
}
