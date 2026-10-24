/**
 * Minimal Markdown for the legal documents (`content/legal/`, section 14.10): headings,
 * paragraphs, bullet lists, pipe tables, **bold** and links. Output is React elements only:
 * raw HTML is shown as text and only relative or https links are kept.
 */

import type { ReactNode } from "react";

export type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; head: string[]; rows: string[][] };

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (line.trim() === "") {
      i += 1;
    } else if (heading) {
      blocks.push({ type: "heading", level: heading[1]?.length ?? 1, text: heading[2] ?? "" });
      i += 1;
    } else if (/^\s*-\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*-\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*-\s+/, "").trim());
        i += 1;
      }
      blocks.push({ type: "list", items });
    } else if (line.trim().startsWith("|")) {
      const head = cells(line);
      i += 1;
      if (/^\s*\|?\s*:?-{3,}/.test(lines[i] ?? "")) i += 1; // separator row
      const rows: string[][] = [];
      while (i < lines.length && (lines[i] ?? "").trim().startsWith("|")) {
        rows.push(cells(lines[i] ?? ""));
        i += 1;
      }
      blocks.push({ type: "table", head, rows });
    } else {
      const text: string[] = [];
      while (i < lines.length) {
        const next = lines[i] ?? "";
        if (next.trim() === "" || /^(#{1,4}\s|\s*-\s|\s*\|)/.test(next)) break;
        text.push(next.trim());
        i += 1;
      }
      blocks.push({ type: "paragraph", text: text.join(" ") });
    }
  }
  return blocks;
}

function safeHref(href: string): string | null {
  return href.startsWith("/") || href.startsWith("https://") ? href : null;
}

/** `**bold**` and `[text](href)`; everything else is plain text (React escapes it). */
export function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] !== undefined) {
      nodes.push(<strong key={key++}>{match[1]}</strong>);
    } else {
      const label = match[2] ?? "";
      const href = safeHref(match[3] ?? "");
      if (href === null) nodes.push(label);
      else if (href.startsWith("https://"))
        nodes.push(
          <a key={key++} href={href} rel="noopener noreferrer">
            {label}
          </a>,
        );
      else
        nodes.push(
          <a key={key++} href={href}>
            {label}
          </a>,
        );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({
  source,
  headingOffset = 0,
}: {
  source: string;
  headingOffset?: number;
}) {
  return (
    <>
      {parseMarkdown(source).map((block, index) => {
        switch (block.type) {
          case "heading": {
            const Tag = `h${String(Math.min(block.level + headingOffset, 6))}` as
              "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
            return <Tag key={index}>{inline(block.text)}</Tag>;
          }
          case "paragraph":
            return <p key={index}>{inline(block.text)}</p>;
          case "list":
            return (
              <ul key={index}>
                {block.items.map((item, j) => (
                  <li key={j}>{inline(item)}</li>
                ))}
              </ul>
            );
          case "table":
            return (
              <div key={index} className="overflow-x-auto">
                <table>
                  <thead>
                    <tr>
                      {block.head.map((cell, j) => (
                        <th key={j} scope="col">
                          {inline(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, j) => (
                      <tr key={j}>
                        {row.map((cell, k) => (
                          <td key={k}>{inline(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </>
  );
}
