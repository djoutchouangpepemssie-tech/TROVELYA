/**
 * Photos sent straight from the browser to object storage (ADR-0019): the API gives a
 * short-lived signed URL, the file goes there by PUT, then the API checks and re-encodes it.
 */

import { apiCall, type ApiResult } from "./api";

export type Variant = { format: string; width: number; height: number; url: string };
export type Media = {
  id: string;
  purpose: string;
  status: string;
  variants: Variant[];
  rejection_reason: string | null;
};
type Upload = { media_id: string; upload_url: string; headers: Record<string, string> };

export type UploadFailure =
  | "empty"
  | "type"
  | "unavailable"
  | "too_large"
  | "rate_limited"
  | "rejected"
  | "timeout"
  | "aborted"
  | "error";
export type UploadResult = { ok: true; media: Media } | { ok: false; reason: UploadFailure };

type Dependencies = {
  api: (path: `/v1/${string}`, init?: RequestInit) => Promise<ApiResult<unknown>>;
  put: (url: string, init: RequestInit) => Promise<Response>;
  sleep: (ms: number) => Promise<void>;
};

const browser: Dependencies = {
  api: (path, init) => apiCall(path, init),
  put: (url, init) => fetch(url, init),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

// The types the API accepts (ADR-0019); the file is checked again once in storage.
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/avif"];
// Processing takes a few seconds (a 12 Mpx photo about 3 s); past a minute the member is told.
const POLL_EVERY_MS = 1000;
const POLL_TRIES = 60;
// A passing error (network, 502) while waiting does not stop the worker: a few are tolerated.
const POLL_ERRORS = 3;
const REFUSED: Record<number, UploadFailure> = {
  404: "unavailable", // flag media.uploads off
  413: "too_large",
  422: "type",
  429: "rate_limited",
};

/** Sends `file` for `purpose` and waits until it is ready to use; stops once `signal` aborts. */
export async function uploadPhoto(
  file: File,
  purpose: "avatar" | "listing",
  deps: Dependencies = browser,
  signal?: AbortSignal,
): Promise<UploadResult> {
  if (file.size === 0) return { ok: false, reason: "empty" };
  if (!ACCEPTED_TYPES.includes(file.type)) return { ok: false, reason: "type" };
  const aborted: UploadResult = { ok: false, reason: "aborted" };
  const asked = await deps.api("/v1/media/uploads", {
    method: "POST",
    body: JSON.stringify({ purpose, mime_type: file.type, bytes: file.size }),
  });
  if (!asked.ok) return { ok: false, reason: REFUSED[asked.status] ?? "error" };
  const upload = asked.data as Upload;
  // The signed headers exactly; the browser sets Content-Length from the body itself.
  const headers = Object.fromEntries(
    Object.entries(upload.headers).filter(([name]) => name.toLowerCase() !== "content-length"),
  );
  try {
    const sent = await deps.put(upload.upload_url, {
      method: "PUT",
      headers,
      body: file,
      ...(signal ? { signal } : {}),
    });
    if (!sent.ok) return { ok: false, reason: "error" };
  } catch {
    return signal?.aborted ? aborted : { ok: false, reason: "error" };
  }
  const path = `/v1/media/${upload.media_id}` as const;
  let state = await deps.api(`${path}/complete`, { method: "POST" });
  for (let tries = 0, errors = 0; ; tries++) {
    if (state.ok) {
      const media = state.data as Media;
      if (media.status === "ready") return { ok: true, media };
      if (media.status === "rejected") return { ok: false, reason: "rejected" };
      errors = 0;
    } else if (++errors > POLL_ERRORS) {
      return { ok: false, reason: "error" };
    }
    if (tries >= POLL_TRIES) return { ok: false, reason: "timeout" };
    await deps.sleep(POLL_EVERY_MS);
    if (signal?.aborted) return aborted;
    state = await deps.api(path);
  }
}

/** The WebP variant sharp at `px` CSS pixels on a high-density screen (or the largest one). */
export function pickVariant(
  variants: Variant[] | null | undefined,
  px: number,
): string | undefined {
  const webp = (variants ?? [])
    .filter((variant) => variant.format === "webp")
    .sort((a, b) => a.width - b.width);
  return (webp.find((variant) => variant.width >= px * 2) ?? webp.at(-1))?.url;
}
