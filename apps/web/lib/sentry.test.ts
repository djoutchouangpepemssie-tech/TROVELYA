import { describe, expect, it } from "vitest";

import { sentryIngestOrigin } from "./sentry";

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
