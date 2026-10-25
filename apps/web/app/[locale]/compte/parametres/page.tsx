import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ProfileSettings } from "./ProfileSettings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Account.profile");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W20, profile: pseudo, name, bio, language and the feed preferences. */
export default function Page() {
  return <ProfileSettings />;
}
