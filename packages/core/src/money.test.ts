import { describe, expect, it } from "vitest";

import { assertMinor, formatMoney } from "./money";

describe("formatMoney", () => {
  it("formats euro cents for French users", () => {
    expect(formatMoney({ amountMinor: 24000, currency: "EUR" }, "fr-FR")).toBe("240,00 €");
  });

  it("uses the currency's own number of decimals", () => {
    expect(formatMoney({ amountMinor: 1500, currency: "JPY" }, "fr-FR")).toBe("1 500 JPY");
  });

  it("refuses non-integer amounts", () => {
    expect(() => formatMoney({ amountMinor: 1.5, currency: "EUR" }, "fr-FR")).toThrow(TypeError);
  });
});

describe("assertMinor", () => {
  it("accepts safe integers", () => {
    expect(() => {
      assertMinor(18500);
    }).not.toThrow();
  });

  it.each([1.5, Number.NaN, Number.POSITIVE_INFINITY, 2 ** 53])("rejects %s", (value) => {
    expect(() => {
      assertMinor(value);
    }).toThrow(TypeError);
  });
});
