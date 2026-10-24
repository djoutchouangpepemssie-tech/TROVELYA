import { describe, expect, it } from "vitest";

import { choicesOf, type ConsentState, needsBanner, recordConsents } from "./consent";

const answered = (version: string): ConsentState => ({
  active_purposes: ["analytics"],
  consents: [
    { purpose: "analytics", granted: false, policy_version: version, created_at: "2026-10-24" },
  ],
});

describe("needsBanner", () => {
  it("stays hidden without an active purpose (Q15), even with no answer", () => {
    expect(needsBanner({ active_purposes: [], consents: [] }, "v1")).toBe(false);
    expect(needsBanner(null, "v1")).toBe(false);
  });

  it("shows while an active purpose has no answer for the current version", () => {
    expect(needsBanner({ active_purposes: ["analytics"], consents: [] }, "v1")).toBe(true);
    expect(needsBanner(answered("v0"), "v1")).toBe(true);
    expect(needsBanner(answered("v1"), "v1")).toBe(false);
  });
});

describe("choicesOf", () => {
  it("reads the latest choices, refused by default", () => {
    expect(choicesOf(answered("v1"))).toEqual({
      analytics: false,
      marketing_email: false,
      personalised_ads: false,
      location: false,
    });
  });
});

describe("recordConsents", () => {
  it("sends the choices one after the other", async () => {
    const order: string[] = [];
    let inFlight = 0;
    const fetcher = async (_path: string, init?: RequestInit) => {
      inFlight += 1;
      expect(inFlight).toBe(1);
      const body = JSON.parse(init?.body as string) as { purpose: string };
      order.push(body.purpose);
      await new Promise((resolve) => setTimeout(resolve, 5));
      inFlight -= 1;
      return new Response(JSON.stringify({ active_purposes: [], consents: [] }), { status: 201 });
    };
    const state = await recordConsents({ analytics: true, personalised_ads: false }, "v1", fetcher);
    expect(order).toEqual(["analytics", "personalised_ads"]);
    expect(state).toEqual({ active_purposes: [], consents: [] });
  });

  it("stops at the first refusal from the server", async () => {
    const fetcher = () => Promise.resolve(new Response("{}", { status: 403 }));
    expect(await recordConsents({ analytics: true }, "v1", fetcher)).toBeNull();
  });
});
