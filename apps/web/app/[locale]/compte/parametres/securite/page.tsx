import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SecuritySettings } from "./SecuritySettings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account.security");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W20, security: e-mail address, connected devices and passkeys. */
export default function Page() {
  return <SecuritySettings />;
}
