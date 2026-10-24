import { describe, expect, it, vi } from "vitest";

import { apiFetch, readCookie } from "./api";

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
