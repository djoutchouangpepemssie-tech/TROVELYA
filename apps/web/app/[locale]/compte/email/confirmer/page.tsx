import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ConfirmEmail } from "./ConfirmEmail";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account.emailConfirm");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** Landing of the link sent to a new address (T05c): no session needed, confirmed on click. */
export default function Page() {
  return <ConfirmEmail />;
}
