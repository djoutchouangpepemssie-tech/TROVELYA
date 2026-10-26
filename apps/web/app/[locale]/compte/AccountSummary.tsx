"use client";

import { Button } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { MemberAvatar } from "@/components/Avatar";

import { useAccount } from "./useAccount";

const SECTIONS = [
  ["profile", "parametres"],
  ["security", "parametres/securite"],
  ["privacy", "parametres/confidentialite"],
  ["data", "donnees"],
] as const;

/** W20: the account hub, then one page per group of settings. */
export function AccountSummary() {
  const t = useTranslations("Account");
  const locale = useLocale();
  const { signOut } = useSession();
  const me = useAccount();
  const [failed, setFailed] = useState(false);

  if (!me) {
    return (
      <main className="mx-auto max-w-xl px-4 py-10" aria-busy="true">
        <p className="text-ink-2">{t("loading")}</p>
      </main>
    );
  }
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-6 px-4 py-8">
      <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
      <div className="flex items-center gap-4">
        <MemberAvatar name={me.display_name} avatar={me.avatar} size={56} />
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{me.display_name}</p>
          <p className="truncate text-ink-2">@{me.username}</p>
          <p className="truncate text-sm text-ink-2">{t("signedInAs", { email: me.email })}</p>
        </div>
      </div>
      <a
        href={`/${locale}/u/${me.username}`}
        className="self-start text-sm font-semibold text-ink underline underline-offset-2"
      >
        {t("publicProfile")}
      </a>

      <nav aria-label={t("navLabel")}>
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
          {SECTIONS.map(([key, path]) => (
            <li key={key}>
              <a
                href={`/${locale}/compte/${path}`}
                className="flex items-center justify-between gap-4 px-4 py-3.5 hover:bg-surface-2"
              >
                <span className="flex flex-col">
                  <span className="font-medium">{t(`nav.${key}`)}</span>
                  <span className="text-sm text-ink-2">{t(`navHints.${key}`)}</span>
                </span>
                <span aria-hidden="true" className="text-ink-3">
                  ›
                </span>
              </a>
            </li>
          ))}
        </ul>
      </nav>

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
