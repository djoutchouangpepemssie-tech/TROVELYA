"use client";

import { useLocale, useTranslations } from "next-intl";

/** Error boundary of the pages under /[locale]: a French message and a way to try again. */
export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("Errors");
  const locale = useLocale();
  return (
    <main className="mx-auto flex min-h-[60dvh] max-w-xl flex-col items-start justify-center gap-4 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t("errorTitle")}</h1>
      <p className="text-ink-2">{t("errorText")}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="trv-button" data-variant="primary" onClick={reset}>
          {t("retry")}
        </button>
        <a href={`/${locale}`} className="trv-button" data-variant="secondary">
          {t("home")}
        </a>
      </div>
    </main>
  );
}
