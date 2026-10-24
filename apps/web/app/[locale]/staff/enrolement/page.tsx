import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { StaffEnrolment } from "./StaffEnrolment";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("StaffEnrolment");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** Staff passkey enrolment (ADR-0018): opened from the link printed by the creation script. */
export default function StaffEnrolmentPage() {
  return <StaffEnrolment />;
}
