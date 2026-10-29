import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ModerationQueue } from "./ModerationQueue";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("StaffModeration");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** The staff's queue of listings awaiting moderation (P2-T05c2, plan Q16, Q41). */
export default function StaffModerationPage() {
  return <ModerationQueue />;
}
