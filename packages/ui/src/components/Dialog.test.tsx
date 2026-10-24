import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";
import { Dialog } from "./Dialog";

function Example() {
  return (
    <Dialog
      trigger={<Button>Ouvrir</Button>}
      title="Confirmer"
      description="Voulez-vous continuer ?"
      closeLabel="Fermer"
    >
      <Button>Valider</Button>
    </Dialog>
  );
}

describe("<Dialog>", () => {
  it("opens, traps focus inside and closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Example />);
    await user.click(screen.getByRole("button", { name: "Ouvrir" }));
    const dialog = screen.getByRole("dialog", { name: "Confirmer" });
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.tab();
    await user.tab();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
