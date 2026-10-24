import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Markdown, parseMarkdown } from "./markdown";

describe("parseMarkdown", () => {
  it("reads headings, paragraphs, lists and tables", () => {
    const blocks = parseMarkdown(
      [
        "# Titre",
        "",
        "Un paragraphe",
        "sur deux lignes.",
        "",
        "## Liste",
        "- un",
        "- deux",
        "",
        "| Nom | Pays |",
        "|---|---|",
        "| Railway | Pays-Bas |",
      ].join("\n"),
    );
    expect(blocks).toEqual([
      { type: "heading", level: 1, text: "Titre" },
      { type: "paragraph", text: "Un paragraphe sur deux lignes." },
      { type: "heading", level: 2, text: "Liste" },
      { type: "list", items: ["un", "deux"] },
      { type: "table", head: ["Nom", "Pays"], rows: [["Railway", "Pays-Bas"]] },
    ]);
  });
});

describe("Markdown", () => {
  it("renders bold text and safe links as React elements", () => {
    const html = renderToStaticMarkup(
      <Markdown
        source={"Voir **la page** [cookies](/fr/legal/cookies) et [IGN](https://www.ign.fr)."}
      />,
    );
    expect(html).toBe(
      '<p>Voir <strong>la page</strong> <a href="/fr/legal/cookies">cookies</a> et ' +
        '<a href="https://www.ign.fr" rel="noopener noreferrer">IGN</a>.</p>',
    );
  });

  it("never renders raw HTML or unsafe links", () => {
    const html = renderToStaticMarkup(
      <Markdown source={'<img src=x onerror="alert(1)"> [x](javascript:alert(1))'} />,
    );
    expect(html).not.toContain("<img");
    expect(html).not.toContain("href");
    expect(html).toContain("&lt;img");
  });

  it("shifts heading levels so the page keeps a single h1", () => {
    const html = renderToStaticMarkup(
      <Markdown source={"# Titre\n\n## Partie"} headingOffset={1} />,
    );
    expect(html).toBe("<h2>Titre</h2><h3>Partie</h3>");
  });
});
