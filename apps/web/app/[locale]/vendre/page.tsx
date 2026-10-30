import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SellFlow } from "@/components/sell/SellFlow";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Sell");
  return { title: t("metaTitle"), robots: { index: false } };
}

/** W09, « Vendre en 30 s » (P2-T09a): photos, then the AI's suggestions, then publication. */
export default function Page() {
  return <SellFlow />;
}
