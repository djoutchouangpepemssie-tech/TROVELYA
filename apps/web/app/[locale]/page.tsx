import { getTranslations } from "next-intl/server";

import { Logo } from "@/components/Logo";

export default async function HomePage() {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex min-h-dvh max-w-xl flex-col items-center justify-center gap-6 px-4 text-center">
      <Logo label={t("logoLabel")} size={72} />
      <h1 className="text-4xl font-semibold tracking-tight">{t("brand")}</h1>
      <p className="text-lg text-ink-2">{t("tagline")}</p>
      <p className="text-ink-2">{t("comingSoon")}</p>
    </main>
  );
}
