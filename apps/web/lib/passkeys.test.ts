import { describe, expect, it, vi } from "vitest";

import {
  enrolStaffPasskey,
  type PasskeyDependencies,
  registerPasskey,
  requestStepUpLink,
  signInWithPasskey,
  stepUpWithPasskey,
} from "./passkeys";

const OPTIONS = { challenge: "Y2hhbGxlbmdl", rpId: "web.example.test" };
const CREDENTIAL = { id: "abc", rawId: "abc", type: "public-key", response: {} };

function json(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function deps(answers: Response[], overrides: Partial<PasskeyDependencies> = {}) {
  const api = vi.fn(() => Promise.resolve(answers.shift() ?? json(500, {})));
  const register = vi.fn(() => Promise.resolve(CREDENTIAL));
  const authenticate = vi.fn(() => Promise.resolve(CREDENTIAL));
  const all = {
    api,
    register,
    authenticate,
    supported: () => true,
    ...overrides,
  } as unknown as PasskeyDependencies;
  return { all, api, register, authenticate };
}

function call(api: ReturnType<typeof vi.fn>, index: number): [string, RequestInit] {
  return api.mock.calls[index] as unknown as [string, RequestInit];
}

describe("registerPasskey", () => {
  it("asks for options, lets the browser create the passkey, then sends it with its name", async () => {
    const d = deps([json(200, OPTIONS), json(201, { id: "p1", name: "Téléphone" })]);
    const result = await registerPasskey("Téléphone", d.all);
    expect(result).toEqual({ ok: true, value: { id: "p1", name: "Téléphone" } });
    expect(call(d.api, 0)).toEqual(["/v1/auth/passkeys/register/options", { method: "POST" }]);
    expect(d.register).toHaveBeenCalledWith({ optionsJSON: OPTIONS });
    const [path, init] = call(d.api, 1);
    expect(path).toBe("/v1/auth/passkeys/register/verify");
    expect(JSON.parse(init.body as string)).toEqual({ credential: CREDENTIAL, name: "Téléphone" });
  });

  it("reports that a recent strong sign-in is needed", async () => {
    const d = deps([json(403, { code: "step_up_required" })]);
    expect(await registerPasskey("x", d.all)).toEqual({ ok: false, error: "step_up_required" });
    expect(d.register).not.toHaveBeenCalled();
  });

  it("reports a cancelled browser prompt without calling the API again", async () => {
    const cancelled = new DOMException("The operation was cancelled", "NotAllowedError");
    const d = deps([json(200, OPTIONS)], { register: vi.fn(() => Promise.reject(cancelled)) });
    expect(await registerPasskey("x", d.all)).toEqual({ ok: false, error: "cancelled" });
    expect(d.api).toHaveBeenCalledOnce();
  });

  it("does nothing when the browser has no WebAuthn", async () => {
    const d = deps([], { supported: () => false });
    expect(await registerPasskey("x", d.all)).toEqual({ ok: false, error: "unsupported" });
    expect(d.api).not.toHaveBeenCalled();
  });
});

describe("signInWithPasskey", () => {
  it("signs in with any passkey of the site", async () => {
    const d = deps([
      json(200, OPTIONS),
      json(200, { user_id: "u1", is_new: false, profile_completed: true }),
    ]);
    expect(await signInWithPasskey(d.all)).toEqual({
      ok: true,
      value: { userId: "u1", profileCompleted: true },
    });
    expect(call(d.api, 0)[0]).toBe("/v1/auth/passkeys/login/options");
    expect(d.authenticate).toHaveBeenCalledWith({ optionsJSON: OPTIONS });
    expect(JSON.parse(call(d.api, 1)[1].body as string)).toEqual({ credential: CREDENTIAL });
  });

  it("maps a refused passkey and a disabled feature", async () => {
    const refused = deps([json(200, OPTIONS), json(400, { code: "passkey_invalid" })]);
    expect(await signInWithPasskey(refused.all)).toEqual({ ok: false, error: "refused" });
    const off = deps([json(404, { code: "not_found" })]);
    expect(await signInWithPasskey(off.all)).toEqual({ ok: false, error: "unavailable" });
  });
});

describe("step-up", () => {
  it("confirms with one of the user's passkeys", async () => {
    const d = deps([json(200, OPTIONS), json(204, null)]);
    expect(await stepUpWithPasskey(d.all)).toEqual({ ok: true, value: undefined });
    expect(call(d.api, 0)[0]).toBe("/v1/auth/step-up/options");
    const [path, init] = call(d.api, 1);
    expect(path).toBe("/v1/auth/step-up");
    expect(JSON.parse(init.body as string)).toEqual({ method: "passkey", credential: CREDENTIAL });
  });

  it("asks for an e-mailed confirmation link", async () => {
    const d = deps([json(202, null)]);
    expect(await requestStepUpLink(d.all)).toEqual({ ok: true, value: undefined });
    expect(JSON.parse(call(d.api, 0)[1].body as string)).toEqual({ method: "magic_link" });
  });

  it("maps rate limiting", async () => {
    const d = deps([json(429, { code: "rate_limited" })]);
    expect(await requestStepUpLink(d.all)).toEqual({ ok: false, error: "rate_limited" });
  });
});

describe("enrolStaffPasskey", () => {
  const TOKEN = "t".repeat(43);

  it("sends the link's token with both requests and signs the staff member in", async () => {
    const d = deps([json(200, OPTIONS), json(200, { user_id: "u1", profile_completed: true })]);
    expect(await enrolStaffPasskey(TOKEN, d.all)).toEqual({ ok: true, value: { userId: "u1" } });
    const [optionsPath, optionsInit] = call(d.api, 0);
    expect(optionsPath).toBe("/v1/auth/passkeys/enrol/options");
    expect(JSON.parse(optionsInit.body as string)).toEqual({ enrolment_token: TOKEN });
    expect(d.register).toHaveBeenCalledWith({ optionsJSON: OPTIONS });
    const [verifyPath, verifyInit] = call(d.api, 1);
    expect(verifyPath).toBe("/v1/auth/passkeys/enrol/verify");
    expect(JSON.parse(verifyInit.body as string)).toEqual({
      enrolment_token: TOKEN,
      credential: CREDENTIAL,
    });
  });

  it("reports a used or expired link", async () => {
    const d = deps([json(400, { code: "enrolment_invalid" })]);
    expect(await enrolStaffPasskey(TOKEN, d.all)).toEqual({ ok: false, error: "link_invalid" });
    expect(d.register).not.toHaveBeenCalled();
  });
});

describe("network down", () => {
  it("answers « unavailable » instead of throwing, at every step", async () => {
    const offline = () => Promise.reject(new TypeError("Failed to fetch"));
    for (const run of [
      (d: PasskeyDependencies) => registerPasskey("Téléphone", d),
      (d: PasskeyDependencies) => signInWithPasskey(d),
      (d: PasskeyDependencies) => stepUpWithPasskey(d),
      (d: PasskeyDependencies) => requestStepUpLink(d),
      (d: PasskeyDependencies) => enrolStaffPasskey("jeton", d),
    ]) {
      const { all } = deps([], { api: vi.fn(offline) as unknown as PasskeyDependencies["api"] });
      await expect(run(all)).resolves.toEqual({ ok: false, error: "unavailable" });
    }
  });

  it("also when only the final check fails", async () => {
    let calls = 0;
    const api = vi.fn(() => {
      calls += 1;
      return calls === 1
        ? Promise.resolve(json(200, OPTIONS))
        : Promise.reject(new TypeError("offline"));
    });
    const { all } = deps([], { api: api as unknown as PasskeyDependencies["api"] });
    await expect(registerPasskey("Téléphone", all)).resolves.toEqual({
      ok: false,
      error: "unavailable",
    });
  });

  it("an empty name is not sent: the screens show a translated default", async () => {
    const { all, api } = deps([json(200, OPTIONS), json(201, { id: "p1", name: null })]);
    await registerPasskey("", all);
    expect(JSON.parse(call(api, 1)[1].body as string)).not.toHaveProperty("name");
  });
});
