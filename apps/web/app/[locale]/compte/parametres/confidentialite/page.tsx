import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PrivacySettings } from "./PrivacySettings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account.privacy");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W20, privacy: the member's consents, and where to read about or act on their data. */
export default function Page() {
  return <PrivacySettings />;
}
