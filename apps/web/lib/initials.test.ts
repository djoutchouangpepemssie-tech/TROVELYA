import { describe, expect, it } from "vitest";

import { initials } from "./initials";

describe("initials", () => {
  it("keeps the first letter of the first two words", () => {
    expect(initials("lucie martin")).toBe("LM");
    expect(initials("Arcel")).toBe("A");
    expect(initials("Jean Paul Sartre")).toBe("JP");
  });

  it("falls back to a question mark", () => {
    expect(initials("   ")).toBe("?");
  });
});
