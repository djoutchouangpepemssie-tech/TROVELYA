import { useLocale, useTranslations } from "next-intl";

/** 404 of every page under /[locale], in the visitor's language. */
export default function NotFound() {
  const t = useTranslations("Errors");
  const locale = useLocale();
  return (
    <main className="mx-auto flex min-h-[60dvh] max-w-xl flex-col items-start justify-center gap-4 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t("notFoundTitle")}</h1>
      <p className="text-ink-2">{t("notFoundText")}</p>
      <a href={`/${locale}`} className="trv-button" data-variant="primary">
        {t("home")}
      </a>
    </main>
  );
}
