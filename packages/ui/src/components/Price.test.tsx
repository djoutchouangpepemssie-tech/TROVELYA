import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Price } from "./Price";

describe("<Price>", () => {
  it("formats integer minor units", () => {
    const { container } = render(<Price amountMinor={24000} currency="EUR" locale="fr-FR" />);
    expect(container.textContent).toBe("240,00 €");
  });

  it("refuses a non-integer amount", () => {
    expect(() => render(<Price amountMinor={1.5} currency="EUR" locale="fr-FR" />)).toThrow(
      TypeError,
    );
  });
});
