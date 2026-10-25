import { afterEach, describe, expect, it, vi } from "vitest";

import { authApi, safeNext } from "./auth";

describe("safeNext", () => {
  it("keeps a path of this site", () => {
    expect(safeNext("/fr")).toBe("/fr");
    expect(safeNext("/fr/compte")).toBe("/fr/compte");
    expect(safeNext("/fr/legal/cookies?x=1")).toBe("/fr/legal/cookies?x=1");
    expect(safeNext("/fr/annonce/objectif-50mm-f1.4")).toBe("/fr/annonce/objectif-50mm-f1.4");
  });

  it("refuses anything that could leave the site", () => {
    for (const value of [
      null,
      "",
      "https://evil.example/",
      "//evil.example",
      "/fr//evil.example",
      "/\\evil.example",
      "javascript:alert(1)",
      "/en/compte",
      "/fr/compte#x",
      " /fr",
      // Dot segments would resolve outside /fr once the browser normalises the path.
      "/fr/../en/compte",
      "/fr/./x",
      "/fr/..",
      "/fr/%2e%2e/api/v1/auth/oauth/google/start",
      "/fr/.%2E/x",
      "/fr/%2E./x",
      "/fr/compte/%2e",
    ]) {
      expect(safeNext(value)).toBeNull();
    }
  });
});

describe("authApi.me", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is null only when the API says signed out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(null, { status: 401 }))),
    );
    expect(await authApi.me()).toBeNull();
  });

  it("is unknown on a server error or a network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 503 }))),
    );
    expect(await authApi.me()).toBeUndefined();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );
    expect(await authApi.me()).toBeUndefined();
  });

  it("returns the member", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(Response.json({ id: "1" }))),
    );
    expect(await authApi.me()).toEqual({ id: "1" });
  });
});
