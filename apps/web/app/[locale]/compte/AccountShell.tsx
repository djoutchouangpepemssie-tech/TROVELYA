"use client";

import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { useAccount } from "./useAccount";

/** Frame of the settings pages: back to the account, the title, then the page once signed in. */
export function AccountShell({ title, children }: { title: string; children: ReactNode }) {
  const t = useTranslations("Account");
  const locale = useLocale();
  const me = useAccount();
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-6 px-4 py-8" aria-busy={!me}>
      <a
        href={`/${locale}/compte`}
        className="self-start text-sm font-medium text-ink-2 hover:text-ink"
      >
        <span aria-hidden="true">‹ </span>
        {t("back")}
      </a>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {me ? children : <p className="text-ink-2">{t("loading")}</p>}
    </main>
  );
}
