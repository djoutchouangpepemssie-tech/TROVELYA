import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { LegalPage } from "@/components/LegalPage";
import { isLegalDocument } from "@/lib/legal";

type Props = { params: Promise<{ locale: string; document: string }> };

// The cookie policy has its own route, with the consent choices.
const DOCUMENTS = new Set(["cgu", "confidentialite", "mentions"]);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { document } = await params;
  if (!DOCUMENTS.has(document) || !isLegalDocument(document)) return {};
  const t = await getTranslations("Legal");
  return { title: t(`titles.${document}`) };
}

export default async function LegalDocumentPage({ params }: Props) {
  const { locale, document } = await params;
  if (!DOCUMENTS.has(document) || !isLegalDocument(document)) notFound();
  return <LegalPage locale={locale} document={document} />;
}
