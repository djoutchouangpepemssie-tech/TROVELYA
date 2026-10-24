import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChoiceTile } from "./ChoiceTile";

describe("<ChoiceTile>", () => {
  it("is a toggle button announcing its state", () => {
    const onPressedChange = vi.fn();
    render(<ChoiceTile label="Mode" pressed={false} onPressedChange={onPressedChange} />);
    const tile = screen.getByRole("button", { name: "Mode" });
    expect(tile.getAttribute("aria-pressed")).toBe("false");
    expect(tile.getAttribute("type")).toBe("button");
    fireEvent.click(tile);
    expect(onPressedChange).toHaveBeenCalledWith(true);
  });

  it("shows the check mark only when pressed, hidden from screen readers", () => {
    const { container, rerender } = render(
      <ChoiceTile label="Collection" pressed={false} onPressedChange={() => undefined} />,
    );
    expect(container.querySelector(".trv-choice-tile-check")).toBeNull();
    rerender(<ChoiceTile label="Collection" pressed onPressedChange={() => undefined} />);
    expect(screen.getByRole("button").getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector(".trv-choice-tile-check")?.getAttribute("aria-hidden")).toBe(
      "true",
    );
  });
});
