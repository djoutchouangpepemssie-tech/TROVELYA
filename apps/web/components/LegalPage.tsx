import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { POLICY_VERSIONS, type LegalDocument } from "@/lib/legal";
import { legalSource } from "@/lib/legal-content";
import { Markdown } from "@/lib/markdown";

/** A legal document with the provisional notice required until a lawyer validates it. */
export async function LegalPage({
  locale,
  document,
  children,
}: {
  locale: string;
  document: LegalDocument;
  children?: ReactNode;
}) {
  const t = await getTranslations("Legal");
  const source = await legalSource(locale, document);
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <p
        role="note"
        className="mb-8 rounded-lg border border-line bg-surface-2 px-4 py-3 text-sm font-medium"
      >
        {t("provisional")}
      </p>
      <article className="trv-prose">
        <Markdown source={source} />
      </article>
      {children}
      <p className="mt-10 text-sm text-ink-2">
        {t("version", { version: POLICY_VERSIONS[document] })}
      </p>
    </main>
  );
}
