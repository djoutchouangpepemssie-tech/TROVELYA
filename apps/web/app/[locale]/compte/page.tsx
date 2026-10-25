import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AccountSummary } from "./AccountSummary";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W20 (first part): the signed-in account. Settings arrive with P1-T12b. */
export default function AccountPage() {
  return <AccountSummary />;
}
