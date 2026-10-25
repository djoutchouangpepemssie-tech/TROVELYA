import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { AuthScreen } from "@/components/AuthScreen";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Auth");
  return { title: t("signUpMeta"), robots: { index: false } };
}

/** W06: sign-in and sign-up share the same journey. */
export default function Page() {
  return (
    <Suspense>
      <AuthScreen mode="signUp" />
    </Suspense>
  );
}
