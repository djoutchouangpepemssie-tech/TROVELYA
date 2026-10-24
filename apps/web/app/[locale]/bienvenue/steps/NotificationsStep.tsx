"use client";

import { Button, Switch } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StepLayout } from "../StepLayout";

const EMAIL_TYPES = [
  ["new_message", "newMessage", true],
  ["price_drop", "priceDrop", false],
  ["nearby_new", "nearbyNew", false],
] as const;

type NotificationsStepProps = {
  error: string | null;
  onSkip: () => void;
  onSave: (email: Record<string, boolean>) => Promise<void>;
};

/** E-mail notifications only: the browser's push permission is asked in P3 (plan P1-T07). */
export function NotificationsStep({ error, onSkip, onSave }: NotificationsStepProps) {
  const t = useTranslations("Onboarding");
  const [email, setEmail] = useState<Record<string, boolean>>(
    Object.fromEntries(EMAIL_TYPES.map(([key, , on]) => [key, on])),
  );
  const [sending, setSending] = useState(false);

  return (
    <StepLayout
      step={4}
      title={t("notifications.title")}
      intro={t("notifications.intro")}
      error={error}
      actions={
        <>
          <Button
            size="lg"
            disabled={sending}
            onClick={() => {
              setSending(true);
              void onSave(email).finally(() => {
                setSending(false);
              });
            }}
          >
            {t("notifications.finish")}
          </Button>
          <Button variant="ghost" onClick={onSkip}>
            {t("skip")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {EMAIL_TYPES.map(([key, label]) => (
          <Switch
            key={key}
            label={t(`notifications.${label}`)}
            checked={email[key] ?? false}
            onCheckedChange={(checked) => {
              setEmail((current) => ({ ...current, [key]: checked }));
            }}
          />
        ))}
      </div>
    </StepLayout>
  );
}
