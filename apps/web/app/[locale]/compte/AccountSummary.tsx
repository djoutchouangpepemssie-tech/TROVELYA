"use client";

import { Button } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/SessionProvider";

export function AccountSummary() {
  const t = useTranslations("Account");
  const locale = useLocale();
  const router = useRouter();
  const { me, signOut } = useSession();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (me === null) router.replace(`/${locale}/connexion?suivant=%2F${locale}%2Fcompte`);
    else if (me && !me.profile_completed) router.replace(`/${locale}/bienvenue`);
  }, [me, router, locale]);

  if (!me) {
    return (
      <main className="mx-auto max-w-xl px-4 py-10" aria-busy="true">
        <p className="text-ink-2">{t("loading")}</p>
      </main>
    );
  }
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
      <p className="text-lg font-medium">{me.display_name}</p>
      <p className="text-ink-2">@{me.username}</p>
      <p className="text-ink-2">{t("signedInAs", { email: me.email })}</p>
      <div>
        <Button
          variant="secondary"
          onClick={() =>
            void (async () => {
              setFailed(!(await signOut(`/${locale}`)));
            })()
          }
        >
          {t("signOut")}
        </Button>
        {failed && (
          <p role="alert" className="mt-2 text-sm text-danger-ink">
            {t("signOutFailed")}
          </p>
        )}
      </div>
    </main>
  );
}
