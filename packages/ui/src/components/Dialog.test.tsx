import { render, screen } from "@testing-library/react";
import { useState } from "react";
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

function OpenedByCode() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        Action sensible
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Confirmer" closeLabel="Fermer">
        <Button>Valider</Button>
      </Dialog>
    </>
  );
}

describe("<Dialog> without a trigger", () => {
  it("opens by code and gives focus back where it was", async () => {
    const user = userEvent.setup();
    render(<OpenedByCode />);
    const action = screen.getByRole("button", { name: "Action sensible" });
    await user.click(action);
    expect(screen.getByRole("dialog", { name: "Confirmer" })).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(action);
  });
});

function DeletesItsOpener() {
  const [open, setOpen] = useState(false);
  const [rowShown, setRowShown] = useState(true);
  return (
    <>
      <h2 tabIndex={-1}>Clés</h2>
      {rowShown && (
        <Button
          onClick={() => {
            setOpen(true);
          }}
        >
          Supprimer
        </Button>
      )}
      <Dialog open={open} onOpenChange={setOpen} title="Supprimer ?" closeLabel="Fermer">
        <Button
          onClick={() => {
            setRowShown(false);
            setOpen(false);
          }}
        >
          Confirmer
        </Button>
      </Dialog>
    </>
  );
}

describe("<Dialog> whose opener is gone", () => {
  it("leaves focus to the page instead of a removed element", async () => {
    const user = userEvent.setup();
    render(<DeletesItsOpener />);
    const opener = screen.getByRole("button", { name: "Supprimer" });
    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener.isConnected).toBe(false);
    expect(document.activeElement).not.toBe(opener);
  });
});
