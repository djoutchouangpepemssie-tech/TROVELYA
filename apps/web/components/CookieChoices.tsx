"use client";

import { Switch } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  choicesOf,
  type ConsentPurpose,
  type ConsentState,
  fetchConsents,
  recordConsents,
} from "@/lib/consent";
import { COOKIE_POLICY_VERSION } from "@/lib/legal";

/** "Gestion des cookies": each optional purpose can be granted or withdrawn in one click. */
export function CookieChoices() {
  const t = useTranslations("Legal");
  const [state, setState] = useState<ConsentState | null>(null);
  const [status, setStatus] = useState<"idle" | "saved" | "failed">("idle");

  useEffect(() => {
    let active = true;
    void fetchConsents().then((loaded) => {
      if (active) setState(loaded);
    });
    return () => {
      active = false;
    };
  }, []);

  async function change(purpose: ConsentPurpose, granted: boolean) {
    const saved = await recordConsents({ [purpose]: granted }, COOKIE_POLICY_VERSION);
    if (saved === null) {
      setStatus("failed");
      return;
    }
    setState(saved);
    setStatus("saved");
  }

  const choices = state ? choicesOf(state) : null;
  return (
    <section aria-labelledby="cookie-choices-title" className="mt-10">
      <h2 id="cookie-choices-title" className="mb-3 text-xl font-semibold">
        {t("choices.title")}
      </h2>
      {state === null || choices === null ? (
        <p className="text-ink-2">{t("choices.loading")}</p>
      ) : state.active_purposes.length === 0 ? (
        <p className="text-ink-2">{t("choices.none")}</p>
      ) : (
        <div className="flex flex-col gap-4">
          {state.active_purposes.map((purpose) => (
            <Switch
              key={purpose}
              label={t(`purposes.${purpose}`)}
              checked={choices[purpose]}
              onCheckedChange={(granted) => void change(purpose, granted)}
            />
          ))}
        </div>
      )}
      <p aria-live="polite" className="mt-3 text-sm">
        {status === "saved" && <span className="text-ink-2">{t("choices.saved")}</span>}
        {status === "failed" && <span className="text-danger-ink">{t("error")}</span>}
      </p>
    </section>
  );
}
