/** Consent choices (P1-T08): read and record through `/v1/me/consents` (signed in or not). */

import { apiFetch } from "./api";

export type ConsentPurpose = "analytics" | "marketing_email" | "personalised_ads" | "location";

export type ConsentRecord = {
  purpose: ConsentPurpose;
  granted: boolean;
  policy_version: string;
  created_at: string;
};

export type ConsentState = { active_purposes: ConsentPurpose[]; consents: ConsentRecord[] };

type Fetch = typeof apiFetch;

export async function fetchConsents(fetcher: Fetch = apiFetch): Promise<ConsentState | null> {
  try {
    const response = await fetcher("/v1/me/consents");
    return response.ok ? ((await response.json()) as ConsentState) : null;
  } catch {
    return null;
  }
}

/**
 * Records the choices one after the other: the first answer of an anonymous visitor sets
 * `__Host-trv_anon`, which the next requests must carry to stay on the same identifier.
 */
export async function recordConsents(
  choices: Partial<Record<ConsentPurpose, boolean>>,
  policyVersion: string,
  fetcher: Fetch = apiFetch,
): Promise<ConsentState | null> {
  let state: ConsentState | null = null;
  for (const [purpose, granted] of Object.entries(choices)) {
    try {
      const response = await fetcher("/v1/me/consents", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ purpose, granted, policy_version: policyVersion }),
      });
      if (!response.ok) return null;
      state = (await response.json()) as ConsentState;
    } catch {
      return null;
    }
  }
  return state;
}

/** Latest choice per purpose (false when never asked). */
export function choicesOf(state: ConsentState): Record<ConsentPurpose, boolean> {
  const choices: Record<ConsentPurpose, boolean> = {
    analytics: false,
    marketing_email: false,
    personalised_ads: false,
    location: false,
  };
  for (const record of state.consents) choices[record.purpose] = record.granted;
  return choices;
}

/**
 * Q15: the banner shows only when a non-essential purpose is active, and asks again when an
 * active purpose has no answer for the current policy version.
 */
export function needsBanner(state: ConsentState | null, policyVersion: string): boolean {
  if (state === null || state.active_purposes.length === 0) return false;
  return state.active_purposes.some(
    (purpose) =>
      !state.consents.some((c) => c.purpose === purpose && c.policy_version === policyVersion),
  );
}
