import { describe, expect, it, vi } from "vitest";

import { relay, type RelayConfig } from "./relay";

const config: RelayConfig = { apiUrl: "https://api.internal.test", proxySecret: "p".repeat(48) };

type Captured = { url: string; init: RequestInit & { headers: Headers } };

function upstream(response: Response) {
  const calls: Captured[] = [];
  const fetchImpl = vi.fn((url: string | URL | Request, init?: RequestInit) => {
    const href = typeof url === "string" ? url : url instanceof URL ? url.href : url.url;
    calls.push({ url: href, init: { ...init, headers: new Headers(init?.headers) } });
    return Promise.resolve(response);
  });
  return { calls, fetchImpl: fetchImpl as unknown as typeof fetch };
}

function browserRequest(path: string, init: RequestInit = {}) {
  return new Request(`https://trovelya.vercel.app/api/${path}`, init);
}

describe("relay", () => {
  it("forwards to the API with only allowed headers and our cookies", async () => {
    const { calls, fetchImpl } = upstream(new Response("{}", { status: 200 }));
    const request = browserRequest("v1/me?x=1", {
      headers: {
        accept: "application/json",
        "accept-language": "fr-FR",
        "x-csrf-token": "t",
        "idempotency-key": "k",
        authorization: "Bearer stolen",
        "x-forwarded-for": "6.6.6.6",
        cookie: "__Host-trv_session=abc; _ga=GA1.2; __Host-trv_csrf=t; NEXT_LOCALE=fr",
      },
    });
    await relay(request, ["v1", "me"], config, fetchImpl);

    expect(calls).toHaveLength(1);
    const [call] = calls;
    expect(call?.url).toBe("https://api.internal.test/v1/me?x=1");
    const headers = call?.init.headers;
    expect(headers?.get("cookie")).toBe("__Host-trv_session=abc; __Host-trv_csrf=t");
    expect(headers?.get("x-csrf-token")).toBe("t");
    expect(headers?.get("idempotency-key")).toBe("k");
    expect(headers?.get("accept-language")).toBe("fr-FR");
    expect(headers?.get("authorization")).toBeNull();
    expect(headers?.get("x-forwarded-for")).toBeNull();
    expect(headers?.get("x-trv-proxy-secret")).toBe(config.proxySecret);
    expect(call?.init.redirect).toBe("manual");
  });

  it("sends the client IP and country set by Vercel, never the browser's own", async () => {
    const { calls, fetchImpl } = upstream(new Response(null, { status: 204 }));
    const request = browserRequest("v1/me", {
      headers: {
        "x-real-ip": "203.0.113.7",
        "x-vercel-ip-country": "FR",
        "x-trv-client-ip": "1.2.3.4",
        "x-trv-proxy-secret": "forged",
      },
    });
    await relay(request, ["v1", "me"], config, fetchImpl);
    const headers = calls[0]?.init.headers;
    expect(headers?.get("x-trv-client-ip")).toBe("203.0.113.7");
    expect(headers?.get("x-trv-client-country")).toBe("FR");
    expect(headers?.get("x-trv-proxy-secret")).toBe(config.proxySecret);
  });

  it("relays the response, every Set-Cookie and redirects", async () => {
    const headers = new Headers({ location: "https://accounts.google.com/o/oauth2" });
    headers.append("set-cookie", "__Host-trv_session=a; Path=/; Secure; HttpOnly");
    headers.append("set-cookie", "__Host-trv_csrf=b; Path=/; Secure");
    const { fetchImpl } = upstream(new Response(null, { status: 302, headers }));
    const response = await relay(
      browserRequest("v1/auth/oauth/google/start"),
      ["v1", "auth", "oauth", "google", "start"],
      config,
      fetchImpl,
    );
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://accounts.google.com/o/oauth2");
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("forwards the body of unsafe methods", async () => {
    const { calls, fetchImpl } = upstream(new Response("{}", { status: 202 }));
    const request = browserRequest("v1/auth/magic-link", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: "a@example.org" }),
    });
    await relay(request, ["v1", "auth", "magic-link"], config, fetchImpl);
    expect(calls[0]?.init.method).toBe("POST");
    expect(new TextDecoder().decode(calls[0]?.init.body as ArrayBuffer)).toBe(
      '{"email":"a@example.org"}',
    );
  });

  it.each([[["admin"]], [["v2", "me"]], [["v1", "..", "health"]], [[]]])(
    "answers 404 for paths outside /api/v1: %j",
    async (path) => {
      const { fetchImpl } = upstream(new Response("{}"));
      const response = await relay(browserRequest(path.join("/")), path, config, fetchImpl);
      expect(response.status).toBe(404);
      expect(response.headers.get("content-type")).toBe("application/problem+json");
      expect(fetchImpl).not.toHaveBeenCalled();
    },
  );

  it("refuses bodies larger than 1 MB", async () => {
    const { fetchImpl } = upstream(new Response("{}"));
    const request = browserRequest("v1/me", { method: "POST", body: "x".repeat(1_048_577) });
    const response = await relay(request, ["v1", "me"], config, fetchImpl);
    expect(response.status).toBe(413);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("answers 502 problem details when the API cannot be reached", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.reject(new TypeError("fetch failed")),
    ) as unknown as typeof fetch;
    const response = await relay(browserRequest("v1/me"), ["v1", "me"], config, fetchImpl);
    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
    expect(((await response.json()) as { code: string }).code).toBe("service_unavailable");
  });

  it("answers 503 when the relay is not configured", async () => {
    const { fetchImpl } = upstream(new Response("{}"));
    const response = await relay(
      browserRequest("v1/me"),
      ["v1", "me"],
      { apiUrl: "", proxySecret: "" },
      fetchImpl,
    );
    expect(response.status).toBe(503);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
