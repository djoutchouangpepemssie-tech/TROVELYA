import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { CookieChoices } from "@/components/CookieChoices";
import { LegalPage } from "@/components/LegalPage";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Legal");
  return { title: t("titles.cookies") };
}

/** Cookie policy and "Gestion des cookies" (always reachable from the footer). */
export default async function CookiesPage({ params }: Props) {
  const { locale } = await params;
  return (
    <LegalPage locale={locale} document="cookies">
      <CookieChoices />
    </LegalPage>
  );
}
