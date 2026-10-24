import { getTranslations } from "next-intl/server";

const LINKS = [
  ["cgu", "cgu"],
  ["confidentialite", "confidentialite"],
  ["cookies", "cookies"],
  ["mentions", "mentions"],
] as const;

/** Legal links on every page; "Gestion des cookies" stays reachable at all times (CNIL). */
export async function SiteFooter({ locale }: { locale: string }) {
  const t = await getTranslations("Legal");
  return (
    <footer className="border-t border-line px-4 py-6 text-sm text-ink-2">
      <nav aria-label={t("footerLabel")} className="mx-auto max-w-5xl">
        <ul className="flex flex-wrap gap-x-6 gap-y-2">
          {LINKS.map(([slug, key]) => (
            <li key={slug}>
              <a className="underline-offset-2 hover:underline" href={`/${locale}/legal/${slug}`}>
                {t(`footer.${key}`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </footer>
  );
}
