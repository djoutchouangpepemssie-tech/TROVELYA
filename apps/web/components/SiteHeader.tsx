"use client";

import { Avatar, Logo } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { useSession } from "./SessionProvider";

function initials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() ?? "");
  return letters.slice(0, 2).join("") || "?";
}

/** Header (6.5) with only what works in P1: the logo, then "Se connecter" or the account. */
export function SiteHeader() {
  const t = useTranslations("Header");
  const locale = useLocale();
  const pathname = usePathname();
  const { me, signOut } = useSession();
  // No member "Se connecter" on the sign-in journey itself, nor in the staff area.
  const onAuthPage = /^\/[a-z]{2}\/(connexion|inscription|verifier|staff)(\/|$)/.test(pathname);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function items(): HTMLElement[] {
      return Array.from(menuRef.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    }
    // Menu pattern (WAI-ARIA): arrows move, Home/End jump, Escape closes, Tab leaves.
    function onKey(event: KeyboardEvent) {
      const list = items();
      const index = list.indexOf(document.activeElement as HTMLElement);
      const move = (to: number) => {
        event.preventDefault();
        list[(to + list.length) % list.length]?.focus();
      };
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      } else if (event.key === "ArrowDown") move(index + 1);
      else if (event.key === "ArrowUp") move(index - 1);
      else if (event.key === "Home") move(0);
      else if (event.key === "End") move(list.length - 1);
      else if (event.key === "Tab") {
        // Leaving the menu: focus goes back to its button, then Tab moves on from there.
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    function onClick(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    menuRef.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  async function leave() {
    if (await signOut(`/${locale}`)) return;
    setFailed(true);
    buttonRef.current?.focus();
    setOpen(false);
  }

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <a href={`/${locale}`} className="flex items-center gap-2 font-semibold">
          <Logo label={t("home")} size={32} />
          <span aria-hidden="true">{t("brand")}</span>
        </a>
        {me === undefined || (me === null && onAuthPage) ? null : me === null ? (
          <a
            href={`/${locale}/connexion`}
            className="rounded-full border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface-2"
          >
            {t("signIn")}
          </a>
        ) : (
          <div ref={menuRef} className="relative">
            <button
              ref={buttonRef}
              type="button"
              aria-haspopup="menu"
              aria-expanded={open}
              aria-controls={open ? menuId : undefined}
              aria-label={t("accountMenu")}
              onClick={() => {
                setOpen((value) => !value);
              }}
              className="rounded-full"
            >
              <Avatar name={me.display_name} initials={initials(me.display_name)} size={36} />
            </button>
            {open && (
              <div className="absolute right-0 mt-2 w-56 rounded-lg border border-line bg-surface p-1 shadow-lg">
                <p className="truncate px-3 py-2 text-sm text-ink-2">{me.display_name}</p>
                <div id={menuId} role="menu" aria-label={t("accountMenu")}>
                  <a
                    role="menuitem"
                    href={`/${locale}/compte`}
                    className="block rounded-md px-3 py-2 text-sm hover:bg-surface-2 focus:bg-surface-2"
                  >
                    {t("account")}
                  </a>
                  <button
                    role="menuitem"
                    type="button"
                    onClick={() => void leave()}
                    className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-surface-2 focus:bg-surface-2"
                  >
                    {t("signOut")}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      {failed && (
        <p role="alert" className="mx-auto max-w-5xl px-4 pb-2 text-sm text-danger-ink">
          {t("signOutFailed")}
        </p>
      )}
    </header>
  );
}
