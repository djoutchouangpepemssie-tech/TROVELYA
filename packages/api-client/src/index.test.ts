import { describe, expect, it } from "vitest";

import { createApiClient } from "./index";

function fakeFetch(handler: (request: Request) => Response) {
  const calls: Request[] = [];
  const fetchImpl = (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    calls.push(request);
    return Promise.resolve(handler(request));
  };
  return { calls, fetchImpl };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("createApiClient", () => {
  it("calls a typed route and returns its body", async () => {
    const { calls, fetchImpl } = fakeFetch(() => json({ status: "ok" }));
    const client = createApiClient("https://api.example.test", { fetch: fetchImpl });
    const { data, error } = await client.GET("/health");
    expect(error).toBeUndefined();
    expect(data).toEqual({ status: "ok" });
    expect(calls[0]?.url).toBe("https://api.example.test/health");
    expect(calls[0]?.credentials).toBe("include");
  });

  it("sends the CSRF token on unsafe methods only", async () => {
    document.cookie = "trv_csrf=token.signature";
    const { calls, fetchImpl } = fakeFetch(() => json({}));
    const client = createApiClient("https://api.example.test", { fetch: fetchImpl });
    await client.GET("/health");
    // POST is checked on a raw request: P0 exposes no typed POST route yet.
    await client.request("post", "/v1/csrf" as never);
    expect(calls[0]?.headers.get("X-CSRF-Token")).toBeNull();
    expect(calls[1]?.headers.get("X-CSRF-Token")).toBe("token.signature");
  });

  it("returns RFC 9457 problem details as the error", async () => {
    const problem = {
      type: "https://docs.trovelya.com/errors/rate_limited",
      status: 429,
      code: "rate_limited",
    };
    const { fetchImpl } = fakeFetch(() => json(problem, 429));
    const client = createApiClient("https://api.example.test", { fetch: fetchImpl });
    const { data, error, response } = await client.GET("/health");
    expect(data).toBeUndefined();
    expect(response.status).toBe(429);
    expect(error).toEqual(problem);
  });
});
