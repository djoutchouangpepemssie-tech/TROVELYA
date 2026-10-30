/** Sign-in screens (P1-T12a): API calls through the relay, and the return address. */

import { apiFetch } from "./api";
import type { Variant } from "./media";

export type AuthMethods = {
  magic_link: boolean;
  magic_link_ttl_min: number;
  passkey: boolean;
  google: boolean;
  apple: boolean;
};
export type Me = {
  id: string;
  email: string;
  username: string;
  display_name: string;
  /** Square variants of the photo (P2-T02c), null while there is none. */
  avatar: Variant[] | null;
  profile_completed: boolean;
  /** Under 18 (null until the birth year is known): may not sell (8.18). */
  is_minor: boolean | null;
  /** The feature flags as they apply to the member (section 7.2). */
  flags: Record<string, boolean>;
  /** Erasure asked for (Q10): the account is erased then, unless the member cancels. */
  erase_at: string | null;
};

const NEXT_KEY = "trv_next";
const SAFE_NEXT = /^\/fr(\/[A-Za-z0-9\-._~%/]*)?(\?[A-Za-z0-9\-._~%=&]*)?$/;

/** A "." or ".." path segment, plain or percent-encoded: the browser would resolve it. */
const DOT_SEGMENT = /\/(\.|%2e){1,2}(\/|\?|$)/i;

/** Only a path of this site ("/fr/…"): never another site, never "//host", never "/fr/..". */
export function safeNext(value: string | null | undefined): string | null {
  if (!value || value.includes("//") || !SAFE_NEXT.test(value) || DOT_SEGMENT.test(value)) {
    return null;
  }
  return value;
}

/** Kept on this device until the e-mailed link is opened (often in another tab). */
export function rememberNext(value: string | null): void {
  try {
    const next = safeNext(value);
    if (next) window.localStorage.setItem(NEXT_KEY, next);
    else window.localStorage.removeItem(NEXT_KEY);
  } catch {
    // Storage blocked: the person lands on the home page instead.
  }
}

export function takeNext(): string | null {
  try {
    const next = safeNext(window.localStorage.getItem(NEXT_KEY));
    window.localStorage.removeItem(NEXT_KEY);
    return next;
  } catch {
    return null;
  }
}

/** Reads the body or releases it: an unread error body keeps the request open. */
async function bodyOrNull<T>(response: Response): Promise<T | null> {
  if (response.ok) return (await response.json()) as T;
  await response.body?.cancel();
  return null;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

export type RequestResult = "sent" | "rate_limited" | "captcha_failed" | "error";
export type VerifyResult =
  | { ok: true; profileCompleted: boolean }
  | { ok: false; error: "invalid" | "rate_limited" | "error" };

export const authApi = {
  async methods(): Promise<AuthMethods | null> {
    try {
      return await bodyOrNull<AuthMethods>(await apiFetch("/v1/auth/methods"));
    } catch {
      return null;
    }
  },

  /** The member, `null` when signed out (401), `undefined` when the answer is unknown. */
  async me(): Promise<Me | null | undefined> {
    try {
      const response = await apiFetch("/v1/me");
      if (response.status === 401) {
        await response.body?.cancel();
        return null;
      }
      return (await bodyOrNull<Me>(response)) ?? undefined;
    } catch {
      return undefined;
    }
  },

  async requestMagicLink(email: string): Promise<RequestResult> {
    try {
      const response = await apiFetch("/v1/auth/magic-link", json({ email }));
      if (response.ok) {
        await response.body?.cancel();
        return "sent";
      }
      if (response.status === 429) {
        await response.body?.cancel();
        return "rate_limited";
      }
      const body = (await response.json().catch(() => ({}))) as { code?: string };
      return body.code === "captcha_failed" ? "captcha_failed" : "error";
    } catch {
      return "error";
    }
  },

  async verify(token: string): Promise<VerifyResult> {
    try {
      const response = await apiFetch("/v1/auth/magic-link/verify", json({ token }));
      if (response.ok) {
        const body = (await response.json()) as { profile_completed: boolean };
        return { ok: true, profileCompleted: body.profile_completed };
      }
      if (response.status === 429) return { ok: false, error: "rate_limited" };
      return {
        ok: false,
        error: response.status === 400 || response.status === 422 ? "invalid" : "error",
      };
    } catch {
      return { ok: false, error: "error" };
    }
  },

  async logout(): Promise<boolean> {
    try {
      const response = await apiFetch("/v1/auth/logout", { method: "POST" });
      await response.body?.cancel();
      return response.ok;
    } catch {
      return false;
    }
  },
};
