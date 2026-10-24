/** API calls of the onboarding (through the same-origin relay, `apiFetch`). */

import { apiFetch } from "@/lib/api";

export type Me = { profile_completed: boolean };

export type Preferences = {
  interests: string[];
  sizes: Record<string, string>;
  budget_max_minor: number | null;
  blocked_brands: string[];
  feed_discovery_level: number;
  paused_categories: string[];
  not_now_until: string | null;
  personalised_feed: boolean;
  notification_settings: Record<string, Record<string, boolean>>;
};

export type Place = {
  label: string;
  place_name: string;
  city: string;
  postal_code: string;
  lat: number;
  lon: number;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; code: string };

async function call<T>(path: `/v1/${string}`, init: RequestInit = {}): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("content-type", "application/json");
  let response: Response;
  try {
    response = await apiFetch(path, { ...init, headers });
  } catch {
    return { ok: false, status: 0, code: "network" };
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string };
    return { ok: false, status: response.status, code: body.code ?? "unknown" };
  }
  const data = (response.status === 204 ? null : await response.json()) as T;
  return { ok: true, data };
}

export const onboardingApi = {
  me: () => call<Me>("/v1/me"),
  usernameSuggestion: () => call<{ username: string }>("/v1/me/username-suggestion"),
  completeProfile: (body: {
    username: string;
    display_name: string;
    birth_year: number;
    accept_terms: true;
    terms_version: string;
  }) => call<Me>("/v1/me/complete-profile", { method: "POST", body: JSON.stringify(body) }),
  preferences: () => call<Preferences>("/v1/me/preferences"),
  savePreferences: (body: Preferences) =>
    call<Preferences>("/v1/me/preferences", { method: "PUT", body: JSON.stringify(body) }),
  searchPlaces: (q: string) => call<{ data: Place[] }>(`/v1/geo/search?q=${encodeURIComponent(q)}`),
  reversePlace: (lat: number, lon: number) =>
    call<Place>(`/v1/geo/reverse?lat=${String(lat)}&lon=${String(lon)}`),
  createZone: (body: {
    label: string;
    place_name: string;
    lat: number;
    lon: number;
    radius_km: number;
  }) => call<unknown>("/v1/me/zones", { method: "POST", body: JSON.stringify(body) }),
};
