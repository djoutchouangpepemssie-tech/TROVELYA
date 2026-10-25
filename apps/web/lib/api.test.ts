import { describe, expect, it, vi } from "vitest";

import { apiCall, apiFetch, prepareCsrf, readCookie } from "./api";

describe("readCookie", () => {
  it("finds a cookie by its exact name", () => {
    expect(readCookie("__Host-trv_csrf", "NEXT_LOCALE=fr; __Host-trv_csrf=a.b")).toBe("a.b");
    expect(readCookie("__Host-trv_csrf", "x__Host-trv_csrf=no")).toBeNull();
  });
});

describe("apiFetch", () => {
  it("calls the same-origin relay and sends no CSRF token on safe methods", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response("{}")));
    await apiFetch("/v1/me", {}, { fetch: fetchImpl, cookies: () => "__Host-trv_csrf=t" });
    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/me");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("x-csrf-token")).toBeNull();
  });

  it("echoes the CSRF cookie on unsafe methods", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response("{}")));
    await apiFetch(
      "/v1/auth/logout",
      { method: "post" },
      { fetch: fetchImpl, cookies: () => "__Host-trv_csrf=t" },
    );
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("x-csrf-token")).toBe("t");
  });

  it("fetches a CSRF token first when the page has none", async () => {
    let cookie = "";
    const fetchImpl = vi.fn((url: string) => {
      if (url === "/api/v1/csrf") cookie = "__Host-trv_csrf=fresh";
      return Promise.resolve(new Response("{}"));
    });
    await apiFetch(
      "/v1/auth/logout",
      { method: "POST" },
      { fetch: fetchImpl, cookies: () => cookie },
    );
    expect(fetchImpl.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/csrf",
      "/api/v1/auth/logout",
    ]);
    const [, init] = fetchImpl.mock.calls[1] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("x-csrf-token")).toBe("fresh");
  });
});

describe("apiCall", () => {
  const deps = (response: Response | Error) => ({
    fetch: vi.fn(() =>
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
    ),
    cookies: () => "__Host-trv_csrf=t",
  });

  it("returns the parsed body and sends JSON", async () => {
    const d = deps(Response.json({ id: "1" }));
    const result = await apiCall<{ id: string }>("/v1/me", { method: "PATCH", body: "{}" }, d);
    expect(result).toEqual({ ok: true, data: { id: "1" } });
    const [, init] = d.fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
  });

  it("returns the status and error code", async () => {
    const d = deps(Response.json({ code: "username_taken" }, { status: 409 }));
    expect(await apiCall("/v1/me", {}, d)).toEqual({
      ok: false,
      status: 409,
      code: "username_taken",
    });
  });

  it("handles no content and network failures", async () => {
    expect(await apiCall("/v1/me", {}, deps(new Response(null, { status: 204 })))).toEqual({
      ok: true,
      data: null,
    });
    expect(await apiCall("/v1/me", {}, deps(new Error("offline")))).toEqual({
      ok: false,
      status: 0,
      code: "network",
    });
  });
});

describe("prepareCsrf", () => {
  it("fetches the token only when the page has none", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response("{}")));
    await prepareCsrf({ fetch: fetchImpl, cookies: () => "__Host-trv_csrf=t" });
    expect(fetchImpl).not.toHaveBeenCalled();
    await prepareCsrf({ fetch: fetchImpl, cookies: () => "" });
    expect(fetchImpl).toHaveBeenCalledWith("/api/v1/csrf", { credentials: "same-origin" });
  });
});
