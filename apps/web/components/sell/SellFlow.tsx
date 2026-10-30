"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import type { SellPhoto } from "@/lib/sell/photos";

import { DetailsStep, type DetailsDone } from "./DetailsStep";
import { PhotoStep } from "./PhotoStep";
import { SellStep } from "./SellStep";

/**
 * W09 (P2-T09a): who may sell, then the steps. Signed-out visitors go to the sign-in page and
 * come back; a member who may not sell yet (profile incomplete, under 18, erasure under way) is
 * told why, with the way to fix it (Q1); without photo uploads (`media.uploads`) nothing starts.
 */
export function SellFlow() {
  const t = useTranslations("Sell");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const { me } = useSession();
  const [photos, setPhotos] = useState<SellPhoto[] | null>(null);
  const [details, setDetails] = useState<DetailsDone | null>(null);

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
  // As the API's own check (Q1): a profile completed, of an adult (an unknown year counts as
  // under 18), without an erasure under way. A suspended account is refused at publication.
  const refusal = !me.profile_completed
    ? { text: "incomplete", link: "bienvenue", label: "complete" }
    : me.is_minor !== false
      ? { text: "minor", link: "", label: "home" }
      : me.erase_at
        ? { text: "erasure", link: "compte/donnees", label: "manage" }
        : null;
  if (refusal) {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-5 pt-14">
        <h1 className="text-3xl leading-tight font-bold tracking-tight">{t("refused.title")}</h1>
        <p>{t(`refused.${refusal.text}`)}</p>
        <a
          href={`/${locale}${refusal.link ? `/${refusal.link}` : ""}`}
          className="trv-button self-start"
          data-variant="primary"
        >
          {t(`refused.${refusal.label}`)}
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
  if (photos === null) return <PhotoStep onDone={setPhotos} />;
  if (details === null) return <DetailsStep photos={photos} onDone={setDetails} />;
  // Step 3 (price, place, handover) comes with P2-T09a3.
  return (
    <SellStep step={3} title={t("price.title")} actions={null}>
      <p>{t("price.soon")}</p>
    </SellStep>
  );
}
