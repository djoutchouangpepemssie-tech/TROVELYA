"use client";

import { Button } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { STEP_UP_RETURN_KEY } from "@/components/StepUp";
import { apiCall } from "@/lib/api";
import { safeNext } from "@/lib/auth";

import { useLinkToken } from "@/components/useLinkToken";

type Step = "reading" | "ready" | "sending" | "done" | "invalid" | "other_device" | "error";

export function ConfirmStepUp() {
  const t = useTranslations("StepUp");
  const locale = useLocale();
  const token = useLinkToken();
  const [step, setStep] = useState<Step>("reading");
  const back = useRef(`/${locale}/compte`);

  useEffect(() => {
    if (token === undefined) return;
    setStep(token ? "ready" : "invalid");
  }, [token]);

  async function confirm() {
    if (!token) return;
    setStep("sending");
    const result = await apiCall<null>("/v1/auth/step-up/verify", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    if (result.ok) {
      try {
        back.current = safeNext(window.localStorage.getItem(STEP_UP_RETURN_KEY)) ?? back.current;
        window.localStorage.removeItem(STEP_UP_RETURN_KEY);
      } catch {
        // Storage blocked: back to the account page.
      }
      setStep("done");
      return;
    }
    if (result.status === 401) setStep("other_device");
    else if (result.status === 400 || result.status === 422) setStep("invalid");
    else setStep("error");
  }

  return (
    <main className="mx-auto flex min-h-[60dvh] w-full max-w-md flex-col justify-center gap-5 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t("confirmTitle")}</h1>
      <div role="status" className="flex flex-col gap-4">
        {step === "done" && (
          <>
            <p className="font-medium">{t("confirmed")}</p>
            <a href={back.current} className="trv-button self-start" data-variant="primary">
              {t("back")}
            </a>
          </>
        )}
      </div>
      {(step === "ready" || step === "sending") && (
        <>
          <p className="text-ink-2">{t("confirmIntro")}</p>
          <Button size="lg" disabled={step === "sending"} onClick={() => void confirm()}>
            {t("confirmSubmit")}
          </Button>
        </>
      )}
      {(step === "invalid" || step === "other_device" || step === "error") && (
        <p role="alert" className="text-danger-ink">
          {t(
            step === "invalid"
              ? "confirmInvalid"
              : step === "other_device"
                ? "confirmOtherDevice"
                : "confirmError",
          )}
        </p>
      )}
    </main>
  );
}
