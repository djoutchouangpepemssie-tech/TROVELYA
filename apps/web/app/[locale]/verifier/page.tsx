import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Verify } from "./Verify";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Auth");
  return { title: t("verifyMeta"), robots: { index: false, follow: false } };
}

/** The e-mailed link lands here; signing in needs a click (mail scanners open links). */
export default function VerifyPage() {
  return <Verify />;
}
