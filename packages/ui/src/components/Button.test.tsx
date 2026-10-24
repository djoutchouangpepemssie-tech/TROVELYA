import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SearchIcon } from "../icons";
import { Button, IconButton } from "./Button";

describe("<Button>", () => {
  it("is a native button of type button by default", () => {
    render(<Button>Vendre</Button>);
    expect(screen.getByRole("button", { name: "Vendre" }).getAttribute("type")).toBe("button");
  });

  it("exposes its variant for styling", () => {
    render(<Button variant="danger">Supprimer</Button>);
    expect(screen.getByRole("button").dataset.variant).toBe("danger");
  });
});

describe("<IconButton>", () => {
  it("is announced with its label", () => {
    render(<IconButton label="Rechercher" icon={<SearchIcon />} />);
    expect(screen.getByRole("button", { name: "Rechercher" })).toBeTruthy();
  });

  it("requires a label (type check)", () => {
    // @ts-expect-error label is mandatory: an icon alone is not accessible.
    render(<IconButton icon={<SearchIcon />} />);
  });
});
