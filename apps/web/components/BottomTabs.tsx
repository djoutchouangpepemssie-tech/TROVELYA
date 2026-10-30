"use client";

import { UserIcon } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { usePathname } from "next/navigation";

import { useSession } from "./SessionProvider";

// Full-screen journeys keep the bottom of the screen for their own actions.
const HIDDEN = /^\/[a-z]{2}\/(bienvenue|connexion|inscription|verifier|staff|vendre)(\/|$)/;

function HomeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <path
        d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Mobile tab bar: only the tabs that exist in P1 (the others come with their phases). */
export function BottomTabs() {
  const t = useTranslations("Header");
  const locale = useLocale();
  const pathname = usePathname();
  const { me } = useSession();
  if (HIDDEN.test(pathname)) return null;
  // The spacer keeps the end of the page (footer, legal links) above the fixed bar.
  const tabs = [
    { href: `/${locale}`, label: t("home"), icon: <HomeIcon /> },
    {
      // Signed out only once the session is known; the account page sends signed-out
      // visitors to the sign-in page itself, so the tab never depends on a pending request.
      href: me === null ? `/${locale}/connexion` : `/${locale}/compte`,
      label: t("profile"),
      icon: <UserIcon size={22} />,
    },
  ];
  return (
    <>
      <div aria-hidden="true" className="h-[calc(4rem+env(safe-area-inset-bottom))] md:hidden" />
      <nav
        aria-label={t("tabsLabel")}
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="mx-auto grid max-w-md grid-cols-2">
          {tabs.map((tab) => {
            // The settings pages belong to the Profil tab too.
            const current =
              pathname === tab.href ||
              (tab.href.endsWith("/compte") && pathname.startsWith(`${tab.href}/`));
            return (
              <li key={tab.label}>
                <a
                  href={tab.href}
                  aria-current={current ? "page" : undefined}
                  className={`flex flex-col items-center gap-1 py-2 text-xs ${current ? "font-semibold text-ink" : "text-ink-2"}`}
                >
                  {tab.icon}
                  {tab.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
