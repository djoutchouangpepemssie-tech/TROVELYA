import { describe, expect, it } from "vitest";

import { hasMalformedEscape } from "./path";

describe("hasMalformedEscape", () => {
  it("accepts plain and well-encoded paths", () => {
    for (const path of ["/fr", "/fr/u/lucie.m", "/fr/u/%C3%A9t%C3%A9", "/fr/legal/cgu"]) {
      expect(hasMalformedEscape(path)).toBe(false);
    }
  });

  it("flags broken escapes", () => {
    for (const path of ["/fr/u/%E0", "/%E0%A4%A", "/fr/%zz", "/fr/%"]) {
      expect(hasMalformedEscape(path)).toBe(true);
    }
  });
});
