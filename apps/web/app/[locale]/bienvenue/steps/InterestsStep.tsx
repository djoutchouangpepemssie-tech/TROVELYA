"use client";

import { Button, ChoiceTile } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StepLayout } from "../StepLayout";

/** Stable keys of the 16 universes (E11), same order as section 8.19. */
export const UNIVERSE_KEYS = [
  "mode",
  "montres_bijoux",
  "maison_jardin",
  "high_tech",
  "culture_loisirs",
  "collection",
  "enfants_bebe",
  "sport_plein_air",
  "art_antiquites",
  "beaute_bien_etre",
  "animaux",
  "materiel_pro",
  "vehicules",
  "immobilier",
  "services",
  "autres",
] as const;

type InterestsStepProps = {
  initial: string[];
  error: string | null;
  onSkip: () => void;
  onSave: (interests: string[]) => Promise<void>;
};

export function InterestsStep({ initial, error, onSkip, onSave }: InterestsStepProps) {
  const t = useTranslations("Onboarding");
  const [chosen, setChosen] = useState<string[]>(initial);
  const [sending, setSending] = useState(false);

  function toggle(key: string, pressed: boolean) {
    setChosen((current) => (pressed ? [...current, key] : current.filter((k) => k !== key)));
  }

  return (
    <StepLayout
      step={2}
      title={t("interests.title")}
      intro={t("interests.intro")}
      error={error}
      actions={
        <>
          <Button
            size="lg"
            disabled={sending}
            onClick={() => {
              setSending(true);
              void onSave(chosen).finally(() => {
                setSending(false);
              });
            }}
          >
            {t("interests.continue", { count: chosen.length })}
          </Button>
          <Button variant="ghost" onClick={onSkip}>
            {t("skip")}
          </Button>
        </>
      }
    >
      <div
        role="group"
        aria-label={t("interests.group")}
        className="grid grid-cols-2 gap-x-2.5 gap-y-3 sm:grid-cols-3 md:grid-cols-4"
      >
        {UNIVERSE_KEYS.map((key) => (
          <ChoiceTile
            key={key}
            label={t(`universes.${key}`)}
            pressed={chosen.includes(key)}
            onPressedChange={(pressed) => {
              toggle(key, pressed);
            }}
          />
        ))}
      </div>
    </StepLayout>
  );
}
