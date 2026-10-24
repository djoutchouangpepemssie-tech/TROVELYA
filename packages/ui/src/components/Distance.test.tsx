import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Distance, roundDistance } from "./Distance";

describe("roundDistance (section 8.11)", () => {
  it.each([
    [0, { kind: "under-1-km" }],
    [800, { kind: "under-1-km" }],
    [999, { kind: "under-1-km" }],
    [1000, { kind: "km", km: 1 }],
    [3400, { kind: "km", km: 3 }],
    [9600, { kind: "km", km: 10 }],
    [12_000, { kind: "km", km: 10 }],
    [13_000, { kind: "km", km: 15 }],
    [97_000, { kind: "km", km: 95 }],
    [100_000, { kind: "km", km: 100 }],
    [392_000, { kind: "km", km: 390 }],
    [396_000, { kind: "km", km: 400 }],
  ])("%i m → %o", (meters, expected) => {
    expect(roundDistance(meters)).toEqual(expected);
  });

  it("rejects negative or non-finite distances", () => {
    expect(() => roundDistance(-1)).toThrow(RangeError);
    expect(() => roundDistance(Number.NaN)).toThrow(RangeError);
  });
});

describe("<Distance>", () => {
  const labels = { underOneKm: "moins de 1 km", km: (km: number) => `${String(km)} km` };

  it("renders the rounded distance with the app's labels", () => {
    render(<Distance meters={392_000} labels={labels} />);
    expect(screen.getByText("390 km")).toBeTruthy();
  });

  it("never renders the exact distance", () => {
    render(<Distance meters={800} labels={labels} />);
    expect(screen.getByText("moins de 1 km")).toBeTruthy();
  });
});
