import { describe, expect, it, vi } from "vitest";

import type { ApiResult } from "./api";
import { pickVariant, uploadPhoto, type Variant } from "./media";

const FILE = new File(["photo"], "moi.jpg", { type: "image/jpeg" });
const UPLOAD = {
  media_id: "m1",
  upload_url: "https://storage.example/originals/k?sig=1",
  headers: { "content-type": "image/jpeg", "content-length": "5" },
  expires_at: "2026-10-26T12:05:00Z",
};

function media(status: string, rejection_reason: string | null = null) {
  return { id: "m1", purpose: "avatar", status, variants: [], rejection_reason };
}

/** An API answering each call in turn, and a storage accepting the PUT. */
function deps(answers: ApiResult<unknown>[], putStatus = 200) {
  const fallback: ApiResult<unknown> = { ok: false, status: 500, code: "unknown" };
  const api = vi.fn<(path: string, init?: RequestInit) => Promise<ApiResult<unknown>>>(() =>
    Promise.resolve(answers.shift() ?? fallback),
  );
  const put = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(new Response(null, { status: putStatus })),
  );
  return { api, put, sleep: vi.fn(() => Promise.resolve()) };
}

describe("uploadPhoto", () => {
  it("asks for an upload URL, sends the file to storage, then waits for processing", async () => {
    const d = deps([
      { ok: true, data: UPLOAD },
      { ok: true, data: media("processing") },
      { ok: true, data: media("processing") },
      { ok: true, data: media("ready") },
    ]);
    const result = await uploadPhoto(FILE, "avatar", d);
    expect(result).toEqual({ ok: true, media: media("ready") });
    const [path, init] = d.api.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/v1/media/uploads");
    expect(JSON.parse(init.body as string)).toEqual({
      purpose: "avatar",
      mime_type: "image/jpeg",
      bytes: 5,
    });
    const [url, putInit] = d.put.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(UPLOAD.upload_url);
    expect(putInit.method).toBe("PUT");
    expect(putInit.body).toBe(FILE);
    // The signed headers exactly; the browser sets the length itself.
    expect(new Headers(putInit.headers).get("content-type")).toBe("image/jpeg");
    expect(new Headers(putInit.headers).has("content-length")).toBe(false);
    expect(d.api.mock.calls.map(([p]) => p).slice(1)).toEqual([
      "/v1/media/m1/complete",
      "/v1/media/m1",
      "/v1/media/m1",
    ]);
  });

  it.each([
    [404, "unavailable"],
    [413, "too_large"],
    [422, "type"],
    [429, "rate_limited"],
    [500, "error"],
  ])("explains a refused upload (%i)", async (status, reason) => {
    const d = deps([{ ok: false, status, code: "x" }]);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: false, reason });
    expect(d.put).not.toHaveBeenCalled();
  });

  it("stops when storage refuses the file", async () => {
    const d = deps([{ ok: true, data: UPLOAD }], 403);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: false, reason: "error" });
    expect(d.api).toHaveBeenCalledOnce();
  });

  it("reports a file refused by processing", async () => {
    const d = deps([
      { ok: true, data: UPLOAD },
      { ok: true, data: media("rejected", "unreadable") },
    ]);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: false, reason: "rejected" });
  });

  it("gives up when processing takes too long", async () => {
    const answers: ApiResult<unknown>[] = [{ ok: true, data: UPLOAD }];
    for (let i = 0; i < 100; i++) answers.push({ ok: true, data: media("processing") });
    const d = deps(answers);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: false, reason: "timeout" });
    expect(d.sleep.mock.calls.length).toBeLessThanOrEqual(60);
  });
});

describe("uploadPhoto, robustness", () => {
  it("tolerates a passing error while waiting for processing", async () => {
    const d = deps([
      { ok: true, data: UPLOAD },
      { ok: false, status: 502, code: "unknown" },
      { ok: false, status: 0, code: "network" },
      { ok: true, data: media("ready") },
    ]);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: true, media: media("ready") });
  });

  it("gives up after errors in a row", async () => {
    const failed: ApiResult<unknown> = { ok: false, status: 502, code: "unknown" };
    const d = deps([{ ok: true, data: UPLOAD }, failed, failed, failed, failed]);
    expect(await uploadPhoto(FILE, "avatar", d)).toEqual({ ok: false, reason: "error" });
  });

  it("refuses an empty file or a type not accepted before any call", async () => {
    for (const [file, reason] of [
      [new File([], "vide.jpg", { type: "image/jpeg" }), "empty"],
      [new File(["x"], "doc.pdf", { type: "application/pdf" }), "type"],
    ] as const) {
      const d = deps([]);
      expect(await uploadPhoto(file, "avatar", d)).toEqual({ ok: false, reason });
      expect(d.api).not.toHaveBeenCalled();
    }
  });

  it("stops once aborted (the page was left)", async () => {
    const controller = new AbortController();
    const d = deps([
      { ok: true, data: UPLOAD },
      { ok: true, data: media("processing") },
    ]);
    d.sleep.mockImplementation(() => {
      controller.abort();
      return Promise.resolve();
    });
    expect(await uploadPhoto(FILE, "avatar", d, controller.signal)).toEqual({
      ok: false,
      reason: "aborted",
    });
    expect(d.api).toHaveBeenCalledTimes(2);
    const [, putInit] = d.put.mock.calls[0] as [string, RequestInit];
    expect(putInit.signal).toBe(controller.signal);
  });
});

describe("pickVariant", () => {
  const variants: Variant[] = [
    { format: "avif", width: 320, height: 320, url: "https://m/a320" },
    { format: "webp", width: 320, height: 320, url: "https://m/w320" },
    { format: "webp", width: 640, height: 640, url: "https://m/w640" },
  ];

  it("takes the smallest WebP sharp on a high-density screen", () => {
    expect(pickVariant(variants, 36)).toBe("https://m/w320");
    expect(pickVariant(variants, 200)).toBe("https://m/w640");
    expect(pickVariant(variants, 400)).toBe("https://m/w640"); // the largest there is
  });

  it("returns nothing without an avatar", () => {
    expect(pickVariant(null, 36)).toBeUndefined();
    expect(pickVariant([], 36)).toBeUndefined();
  });
});
