import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Onboarding } from "./Onboarding";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Onboarding");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W07: onboarding after the first sign-in (Q12: profile, interests, zone, notifications). */
export default function WelcomePage() {
  return <Onboarding />;
}
