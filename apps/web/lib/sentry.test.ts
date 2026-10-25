import { describe, expect, it } from "vitest";

import { scrubSecrets, sentryIngestOrigin, sentryOptions } from "./sentry";

describe("sentryIngestOrigin", () => {
  it("keeps only the scheme and host of the DSN (the public key is not needed in the CSP)", () => {
    expect(
      sentryIngestOrigin("https://e3816d00@o4512310271344640.ingest.de.sentry.io/4512310361784400"),
    ).toBe("https://o4512310271344640.ingest.de.sentry.io");
  });

  it("returns nothing without a DSN or with an invalid one", () => {
    expect(sentryIngestOrigin(undefined)).toBe("");
    expect(sentryIngestOrigin("")).toBe("");
    expect(sentryIngestOrigin("not a url")).toBe("");
  });
});

describe("scrubSecrets", () => {
  it("removes sign-in and enrolment tokens from URLs, wherever they sit in the event", () => {
    const event = {
      request: { url: "https://trovelya.eu/fr/verifier#token=abc_DEF-123" },
      breadcrumbs: [
        {
          category: "navigation",
          data: { from: "/fr/staff/enrolement#token=zzz", to: "/fr/verifier?token=q1&x=2" },
        },
      ],
      message: "échec pour token=secret",
    };
    const scrubbed = JSON.stringify(scrubSecrets(event));
    for (const secret of ["abc_DEF-123", "zzz", "q1", "secret"]) {
      expect(scrubbed).not.toContain(secret);
    }
    expect(scrubbed).toContain("/fr/verifier#token=[filtré]");
    expect(scrubbed).toContain("&x=2");
  });

  it("leaves an event without a token unchanged", () => {
    const event = { message: "erreur réseau", tags: { page: "/fr/compte" } };
    expect(scrubSecrets(event)).toEqual(event);
  });

  it("is applied before every breadcrumb, error and trace leaves the browser", () => {
    const options = sentryOptions();
    const crumb = { data: { from: "/fr/verifier#token=abc" } };
    expect(JSON.stringify(options.beforeBreadcrumb(crumb))).not.toContain("abc");
    expect(JSON.stringify(options.beforeSend({ message: "token=abc" }))).not.toContain("abc");
    expect(
      JSON.stringify(options.beforeSendTransaction({ transaction: "/fr/verifier#token=abc" })),
    ).not.toContain("abc");
  });
});

describe("scrubSecrets on what cannot be checked", () => {
  it("drops a circular value rather than sending it unchecked", () => {
    const circular: Record<string, unknown> = { url: "/fr/verifier#token=abc" };
    circular.self = circular;
    expect(scrubSecrets(circular)).toBeNull();
  });
});
