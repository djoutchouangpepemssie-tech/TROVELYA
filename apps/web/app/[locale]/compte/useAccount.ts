"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useSession } from "@/components/SessionProvider";
import type { Me } from "@/lib/auth";

/**
 * The signed-in member for the account pages: signed-out visitors go to the sign-in page
 * (and come back here), members without a profile go to the welcome steps.
 * `null` while loading or leaving.
 */
export function useAccount(): Me | null {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const { me } = useSession();

  useEffect(() => {
    if (me === null) router.replace(`/${locale}/connexion?suivant=${encodeURIComponent(pathname)}`);
    else if (me && !me.profile_completed) router.replace(`/${locale}/bienvenue`);
  }, [me, router, locale, pathname]);

  return me?.profile_completed ? me : null;
}
