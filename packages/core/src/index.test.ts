import { describe, expect, it } from "vitest";

import { PACKAGE_NAME } from "./index";

// Placeholder test proving the toolchain runs; replaced by money.test.ts in P0-T05.
describe("@trovelya/core", () => {
  it("exposes its package name", () => {
    expect(PACKAGE_NAME).toBe("@trovelya/core");
  });
});
