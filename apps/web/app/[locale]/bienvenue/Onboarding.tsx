"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { onboardingApi, type Preferences } from "./api";
import { InterestsStep } from "./steps/InterestsStep";
import { NotificationsStep } from "./steps/NotificationsStep";
import { ProfileStep } from "./steps/ProfileStep";
import { ZoneStep } from "./steps/ZoneStep";

type Step = 1 | 2 | 3 | 4;

/** W07 (Q12): 1. profile (required), 2. interests, 3. zone and sizes, 4. notifications.
 * Steps 2 to 4 can be skipped. Preferences are replaced as a whole (PUT), so the screen keeps
 * the saved ones and changes only its own fields. */
export function Onboarding() {
  const t = useTranslations("Onboarding");
  const locale = useLocale();
  const router = useRouter();
  const [step, setStep] = useState<Step | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [error, setError] = useState<string | null>(null);

  const home = `/${locale}`;

  useEffect(() => {
    const effect = { active: true };
    void (async () => {
      const me = await onboardingApi.me();
      if (!effect.active) return;
      if (!me.ok) {
        router.replace(home);
        return;
      }
      setStep(me.data.profile_completed ? 2 : 1);
    })();
    return () => {
      effect.active = false;
    };
  }, [home, router]);

  useEffect(() => {
    if (step === null || step === 1 || preferences !== null) return;
    void (async () => {
      const saved = await onboardingApi.preferences();
      if (saved.ok) setPreferences(saved.data);
      else setError(t("error"));
    })();
  }, [step, preferences, t]);

  async function save(changes: Partial<Preferences>): Promise<boolean> {
    if (!preferences) return false;
    const next = { ...preferences, ...changes };
    const saved = await onboardingApi.savePreferences(next);
    if (!saved.ok) {
      setError(t("error"));
      return false;
    }
    setPreferences(saved.data);
    return true;
  }

  function goTo(next: Step) {
    setError(null);
    setStep(next);
  }

  function finish() {
    router.push(home);
  }

  if (step === null) {
    return (
      <main className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <p className="text-ink-2">{t("loading")}</p>
      </main>
    );
  }
  if (step === 1) {
    return (
      <ProfileStep
        onCompleted={() => {
          goTo(2);
        }}
      />
    );
  }
  if (step === 2) {
    return (
      <InterestsStep
        initial={preferences?.interests ?? []}
        error={error}
        onSkip={() => {
          goTo(3);
        }}
        onSave={async (interests) => {
          if (await save({ interests })) goTo(3);
        }}
      />
    );
  }
  if (step === 3) {
    return (
      <ZoneStep
        error={error}
        onError={setError}
        onSkip={() => {
          goTo(4);
        }}
        onSave={async (sizes) => {
          if (Object.keys(sizes).length === 0 || (await save({ sizes }))) goTo(4);
        }}
      />
    );
  }
  return (
    <NotificationsStep
      error={error}
      onSkip={finish}
      onSave={async (email) => {
        const settings = { ...(preferences?.notification_settings ?? {}), email };
        if (await save({ notification_settings: settings })) finish();
      }}
    />
  );
}
