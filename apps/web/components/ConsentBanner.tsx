"use client";

import { Button, Dialog, Switch } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  choicesOf,
  type ConsentPurpose,
  type ConsentState,
  fetchConsents,
  needsBanner,
  recordConsents,
} from "@/lib/consent";
import { COOKIE_POLICY_VERSION } from "@/lib/legal";

/**
 * CNIL banner (13.3): "Tout accepter", "Tout refuser" and "Personnaliser" with the same size
 * and contrast; nothing optional is used before an answer. Hidden while no non-essential
 * purpose is active (Q15: none in P1).
 */
export function ConsentBanner() {
  const t = useTranslations("Legal");
  const locale = useLocale();
  const [state, setState] = useState<ConsentState | null>(null);
  const [choices, setChoices] = useState<Partial<Record<ConsentPurpose, boolean>>>({});
  const [customising, setCustomising] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    void fetchConsents().then((loaded) => {
      if (!active || loaded === null) return;
      setState(loaded);
      const current = choicesOf(loaded);
      setChoices(Object.fromEntries(loaded.active_purposes.map((p) => [p, current[p]])));
    });
    return () => {
      active = false;
    };
  }, []);

  if (!needsBanner(state, COOKIE_POLICY_VERSION) || state === null) return null;
  const purposes = state.active_purposes;

  async function answer(next: Partial<Record<ConsentPurpose, boolean>>) {
    const saved = await recordConsents(next, COOKIE_POLICY_VERSION);
    if (saved === null) {
      setFailed(true);
      return;
    }
    setCustomising(false);
    setState(saved);
  }

  const all = (granted: boolean) => Object.fromEntries(purposes.map((p) => [p, granted]));

  return (
    <section
      aria-labelledby="consent-banner-title"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface p-4 shadow-lg"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        <h2 id="consent-banner-title" className="font-semibold">
          {t("banner.title")}
        </h2>
        <p className="text-sm text-ink-2">
          {t("banner.body")}{" "}
          <a className="underline" href={`/${locale}/legal/cookies`}>
            {t("banner.more")}
          </a>
        </p>
        {failed && (
          <p role="alert" className="text-sm text-danger-ink">
            {t("error")}
          </p>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Button variant="secondary" onClick={() => void answer(all(true))}>
            {t("banner.acceptAll")}
          </Button>
          <Button variant="secondary" onClick={() => void answer(all(false))}>
            {t("banner.refuseAll")}
          </Button>
          <Dialog
            open={customising}
            onOpenChange={setCustomising}
            title={t("banner.customiseTitle")}
            closeLabel={t("close")}
            trigger={<Button variant="secondary">{t("banner.customise")}</Button>}
          >
            <div className="flex flex-col gap-4">
              {purposes.map((purpose) => (
                <Switch
                  key={purpose}
                  label={t(`purposes.${purpose}`)}
                  checked={choices[purpose] ?? false}
                  onCheckedChange={(checked) => {
                    setChoices((current) => ({ ...current, [purpose]: checked }));
                  }}
                />
              ))}
              <Button onClick={() => void answer(choices)}>{t("banner.save")}</Button>
            </div>
          </Dialog>
        </div>
      </div>
    </section>
  );
}
