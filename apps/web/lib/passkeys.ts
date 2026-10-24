/**
 * Passkeys in the browser (P1-T04): WebAuthn ceremonies around the API's options and checks.
 *
 * The browser prompt (fingerprint, face, device PIN) is shown by `@simplewebauthn/browser`;
 * every call goes through `apiFetch` (same-origin relay and CSRF). Results never throw: the
 * screens turn `error` into a French message.
 */

import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";

import { apiFetch } from "./api";

export type PasskeyError =
  | "unsupported" // no WebAuthn in this browser
  | "cancelled" // the person closed the browser prompt, or it timed out
  | "refused" // the API rejected the passkey (passkey_invalid)
  | "step_up_required" // a recent strong sign-in is needed first
  | "rate_limited"
  | "link_invalid" // staff enrolment link used or expired
  | "unavailable"; // feature off (404) or any other failure

export type PasskeyResult<T> = { ok: true; value: T } | { ok: false; error: PasskeyError };

export type PasskeyDependencies = {
  api: typeof apiFetch;
  register: typeof startRegistration;
  authenticate: typeof startAuthentication;
  supported: () => boolean;
};

const browser: PasskeyDependencies = {
  api: apiFetch,
  register: startRegistration,
  authenticate: startAuthentication,
  supported: browserSupportsWebAuthn,
};

function failure<T>(error: PasskeyError): PasskeyResult<T> {
  return { ok: false, error };
}

async function apiError<T>(response: Response): Promise<PasskeyResult<T>> {
  if (response.status === 429) return failure("rate_limited");
  const body = (await response.json().catch(() => ({}))) as { code?: string };
  if (body.code === "passkey_invalid") return failure("refused");
  if (body.code === "step_up_required") return failure("step_up_required");
  if (body.code === "enrolment_invalid") return failure("link_invalid");
  return failure("unavailable");
}

function post(deps: PasskeyDependencies, path: `/v1/${string}`, body?: unknown) {
  if (body === undefined) return deps.api(path, { method: "POST" });
  return deps.api(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Options from the API, then the browser prompt; the credential to send back. */
async function ceremony<T>(
  deps: PasskeyDependencies,
  optionsPath: `/v1/${string}`,
  run: (options: never) => Promise<T>,
  optionsBody?: unknown,
): Promise<PasskeyResult<T>> {
  if (!deps.supported()) return failure("unsupported");
  const response = await post(deps, optionsPath, optionsBody);
  if (!response.ok) return apiError(response);
  const options = (await response.json()) as never;
  try {
    return { ok: true, value: await run(options) };
  } catch (error) {
    const name = error instanceof DOMException || error instanceof Error ? error.name : "";
    return failure(
      name === "NotAllowedError" || name === "AbortError" ? "cancelled" : "unavailable",
    );
  }
}

export async function registerPasskey(
  name: string,
  deps: PasskeyDependencies = browser,
): Promise<PasskeyResult<{ id: string; name: string | null }>> {
  const created = await ceremony(deps, "/v1/auth/passkeys/register/options", (optionsJSON) =>
    deps.register({ optionsJSON }),
  );
  if (!created.ok) return created;
  const response = await post(deps, "/v1/auth/passkeys/register/verify", {
    credential: created.value,
    name,
  });
  if (!response.ok) return apiError(response);
  return { ok: true, value: (await response.json()) as { id: string; name: string | null } };
}

export async function signInWithPasskey(
  deps: PasskeyDependencies = browser,
): Promise<PasskeyResult<{ userId: string; profileCompleted: boolean }>> {
  const asserted = await ceremony(deps, "/v1/auth/passkeys/login/options", (optionsJSON) =>
    deps.authenticate({ optionsJSON }),
  );
  if (!asserted.ok) return asserted;
  const response = await post(deps, "/v1/auth/passkeys/login/verify", {
    credential: asserted.value,
  });
  if (!response.ok) return apiError(response);
  const body = (await response.json()) as { user_id: string; profile_completed: boolean };
  return { ok: true, value: { userId: body.user_id, profileCompleted: body.profile_completed } };
}

/** Renew the strong sign-in with one of the signed-in user's passkeys (new session cookie). */
export async function stepUpWithPasskey(
  deps: PasskeyDependencies = browser,
): Promise<PasskeyResult<void>> {
  const asserted = await ceremony(deps, "/v1/auth/step-up/options", (optionsJSON) =>
    deps.authenticate({ optionsJSON }),
  );
  if (!asserted.ok) return asserted;
  const response = await post(deps, "/v1/auth/step-up", {
    method: "passkey",
    credential: asserted.value,
  });
  return response.ok ? { ok: true, value: undefined } : apiError(response);
}

/** Without a passkey: a confirmation link is e-mailed to the account's address. */
export async function requestStepUpLink(
  deps: PasskeyDependencies = browser,
): Promise<PasskeyResult<void>> {
  const response = await post(deps, "/v1/auth/step-up", { method: "magic_link" });
  return response.ok ? { ok: true, value: undefined } : apiError(response);
}

/** Staff enrolment (ADR-0018): the first passkey of a staff account, from the script's link. */
export async function enrolStaffPasskey(
  enrolmentToken: string,
  deps: PasskeyDependencies = browser,
): Promise<PasskeyResult<{ userId: string }>> {
  const created = await ceremony(
    deps,
    "/v1/auth/passkeys/enrol/options",
    (optionsJSON) => deps.register({ optionsJSON }),
    { enrolment_token: enrolmentToken },
  );
  if (!created.ok) return created;
  const response = await post(deps, "/v1/auth/passkeys/enrol/verify", {
    enrolment_token: enrolmentToken,
    credential: created.value,
  });
  if (!response.ok) return apiError(response);
  const body = (await response.json()) as { user_id: string };
  return { ok: true, value: { userId: body.user_id } };
}
