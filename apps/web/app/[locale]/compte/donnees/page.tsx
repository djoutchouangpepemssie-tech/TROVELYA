import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { DataSettings } from "./DataSettings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account.data");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W20, data (GDPR articles 17 and 20): export the account's data, or erase the account. */
export default function Page() {
  return <DataSettings />;
}
