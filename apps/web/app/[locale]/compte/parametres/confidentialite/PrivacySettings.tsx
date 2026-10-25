"use client";

import { Button, Switch } from "@trovelya/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  type ConsentPurpose,
  type ConsentRecord,
  type ConsentState,
  fetchConsents,
  recordConsents,
} from "@/lib/consent";
import { COOKIE_POLICY_VERSION, PRIVACY_POLICY_VERSION } from "@/lib/legal";

import { AccountShell } from "../../AccountShell";

const PURPOSES: ConsentPurpose[] = ["analytics", "marketing_email", "personalised_ads", "location"];

/**
 * Consents of the signed-in member: every purpose offered today, and every purpose they once
 * answered (a consent given must stay as easy to withdraw, even if no longer asked for).
 */
export function PrivacySettings() {
  const t = useTranslations("Account.privacy");
  const tLegal = useTranslations("Legal");
  const tAccount = useTranslations("Account");
  const format = useFormatter();
  const locale = useLocale();
  const [state, setState] = useState<ConsentState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [notice, setNotice] = useState<"saved" | "failed" | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    const loaded = await fetchConsents();
    if (loaded) setState(loaded);
    else setLoadFailed(true);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function change(purpose: ConsentPurpose, granted: boolean) {
    setNotice(null);
    // The location consent is given under the privacy policy, the others under the cookie one.
    const version = purpose === "location" ? PRIVACY_POLICY_VERSION : COOKIE_POLICY_VERSION;
    const saved = await recordConsents({ [purpose]: granted }, version);
    if (saved === null) {
      setNotice("failed");
      return;
    }
    setState(saved);
    setNotice("saved");
  }

  const latest = (purpose: ConsentPurpose): ConsentRecord | undefined =>
    state?.consents.find((record) => record.purpose === purpose);
  const shown = state
    ? PURPOSES.filter(
        (purpose) => state.active_purposes.includes(purpose) || latest(purpose) !== undefined,
      )
    : [];

  function answered(record: ConsentRecord | undefined): string {
    if (!record) return t("never");
    const date = format.dateTime(new Date(record.created_at), { dateStyle: "long" });
    return t(record.granted ? "granted" : "refused", { date });
  }

  return (
    <AccountShell title={t("title")}>
      <section aria-labelledby="consents-title" className="flex flex-col gap-4">
        <h2 id="consents-title" className="text-xl font-semibold">
          {t("consentsTitle")}
        </h2>
        <p className="text-sm text-ink-2">{t("consentsIntro")}</p>
        {loadFailed && (
          <div role="alert" className="flex flex-col items-start gap-2">
            <p className="text-danger-ink">{t("loadError")}</p>
            <Button variant="secondary" onClick={() => void load()}>
              {tAccount("retry")}
            </Button>
          </div>
        )}
        {state && shown.length === 0 && <p className="text-ink-2">{t("none")}</p>}
        {shown.map((purpose) => (
          <div key={purpose} className="flex flex-col gap-1">
            <Switch
              label={tLegal(`purposes.${purpose}`)}
              checked={latest(purpose)?.granted ?? false}
              onCheckedChange={(granted) => void change(purpose, granted)}
            />
            <p className="text-sm text-ink-2">{answered(latest(purpose))}</p>
          </div>
        ))}
        <p aria-live="polite" className="text-sm">
          {notice === "saved" && <span className="text-ink-2">{t("saved")}</span>}
          {notice === "failed" && <span className="text-danger-ink">{t("error")}</span>}
        </p>
      </section>

      <section
        aria-labelledby="privacy-links-title"
        className="flex flex-col gap-3 border-t border-line pt-6"
      >
        <h2 id="privacy-links-title" className="text-xl font-semibold">
          {t("linksTitle")}
        </h2>
        <ul className="flex flex-col gap-2">
          {(
            [
              ["policy", `/${locale}/legal/confidentialite`],
              ["cookies", `/${locale}/legal/cookies`],
              ["data", `/${locale}/compte/donnees`],
            ] as const
          ).map(([key, href]) => (
            <li key={key}>
              <a href={href} className="font-medium underline underline-offset-2">
                {t(key)}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </AccountShell>
  );
}
