// Server code only (reads the file system).
import { readFile } from "node:fs/promises";
import path from "node:path";

import type { LegalDocument } from "./legal";

/** Markdown source of a legal document (bundled with the server: see next.config.ts). */
export async function legalSource(locale: string, document: LegalDocument): Promise<string> {
  return readFile(path.join(process.cwd(), "content", "legal", locale, `${document}.md`), "utf8");
}
