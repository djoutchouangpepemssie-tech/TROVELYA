"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import type { SellPhoto } from "@/lib/sell/photos";

import { PhotoStep } from "./PhotoStep";

/**
 * W09 (P2-T09a): who may sell, then the steps. Signed-out visitors go to the sign-in page and
 * come back; a member who may not sell yet (profile incomplete, under 18) is told why, with
 * the way to fix it (Q1); without photo uploads (flag `media.uploads`) nothing can start.
 */
export function SellFlow() {
  const t = useTranslations("Sell");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const { me } = useSession();
  const [, setPhotos] = useState<SellPhoto[]>([]);

  useEffect(() => {
    if (me === null) router.replace(`/${locale}/connexion?suivant=${encodeURIComponent(pathname)}`);
  }, [me, router, locale, pathname]);

  if (!me) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 pt-14" aria-busy="true">
        <p className="text-ink-2">{t("loading")}</p>
      </main>
    );
  }
  if (!me.profile_completed || me.is_minor) {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-5 pt-14">
        <h1 className="text-3xl leading-tight font-bold tracking-tight">{t("refused.title")}</h1>
        <p>{me.is_minor ? t("refused.minor") : t("refused.incomplete")}</p>
        <a
          href={me.is_minor ? `/${locale}` : `/${locale}/bienvenue`}
          className="trv-button self-start"
          data-variant="primary"
        >
          {me.is_minor ? t("refused.home") : t("refused.complete")}
        </a>
      </main>
    );
  }
  if (!me.flags["media.uploads"]) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 pt-14">
        <h1 className="text-3xl leading-tight font-bold tracking-tight">{t("metaTitle")}</h1>
        <p className="mt-3">{t("unavailable")}</p>
      </main>
    );
  }
  return <PhotoStep onDone={setPhotos} />;
}
