"use client";

import { Button } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { useLinkToken } from "@/components/useLinkToken";
import { apiCall } from "@/lib/api";

type Step = "reading" | "ready" | "sending" | "done" | "invalid" | "taken" | "error";

export function ConfirmEmail() {
  const t = useTranslations("Account.emailConfirm");
  const locale = useLocale();
  const { refresh } = useSession();
  const token = useLinkToken();
  const [step, setStep] = useState<Step>("reading");

  useEffect(() => {
    if (token === undefined) return;
    setStep(token ? "ready" : "invalid");
  }, [token]);

  async function confirm() {
    if (!token) return;
    setStep("sending");
    const result = await apiCall<null>("/v1/auth/email-change/verify", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    if (result.ok) {
      setStep("done");
      await refresh(); // A signed-in page shows the new address.
      return;
    }
    if (result.code === "email_taken") setStep("taken");
    else if (result.status === 400 || result.status === 422) setStep("invalid");
    else setStep("error");
  }

  return (
    <main className="mx-auto flex min-h-[60dvh] w-full max-w-md flex-col justify-center gap-5 px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
      <div role="status" className="flex flex-col gap-4">
        {step === "done" && (
          <>
            <p className="font-medium">{t("done")}</p>
            <a href={`/${locale}/compte`} className="trv-button self-start" data-variant="primary">
              {t("toAccount")}
            </a>
          </>
        )}
      </div>
      {(step === "ready" || step === "sending") && (
        <>
          <p className="text-ink-2">{t("intro")}</p>
          <Button size="lg" disabled={step === "sending"} onClick={() => void confirm()}>
            {t("submit")}
          </Button>
        </>
      )}
      {(step === "invalid" || step === "taken" || step === "error") && (
        <p role="alert" className="text-danger-ink">
          {t(step)}
        </p>
      )}
    </main>
  );
}
