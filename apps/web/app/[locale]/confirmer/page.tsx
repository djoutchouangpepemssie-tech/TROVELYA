import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ConfirmStepUp } from "./ConfirmStepUp";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("StepUp");
  return { title: t("confirmMeta"), robots: { index: false } };
}

/** Landing of the step-up link (13.2): confirms on click, then back to the sensitive action. */
export default function Page() {
  return <ConfirmStepUp />;
}
