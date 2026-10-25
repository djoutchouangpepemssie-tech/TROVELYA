"use client";

import { Button, Logo } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { useLinkToken } from "@/components/useLinkToken";
import { authApi, takeNext } from "@/lib/auth";

type State =
  | { step: "reading" }
  | { step: "ready"; token: string; sending: boolean; error: "rate_limited" | "error" | null }
  | { step: "invalid" };

export function Verify() {
  const t = useTranslations("Auth");
  const locale = useLocale();
  const router = useRouter();
  const { refresh } = useSession();
  const [state, setState] = useState<State>({ step: "reading" });
  const token = useLinkToken();

  useEffect(() => {
    if (token === undefined) return;
    setState(token ? { step: "ready", token, sending: false, error: null } : { step: "invalid" });
  }, [token]);

  async function signIn(token: string) {
    setState({ step: "ready", token, sending: true, error: null });
    const result = await authApi.verify(token);
    if (!result.ok) {
      setState(
        result.error === "invalid"
          ? { step: "invalid" }
          : { step: "ready", token, sending: false, error: result.error },
      );
      return;
    }
    await refresh();
    // A new member goes through the welcome first; the return address waits for its end.
    router.replace(result.profileCompleted ? (takeNext() ?? `/${locale}`) : `/${locale}/bienvenue`);
  }

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-3.5rem)] w-full max-w-md flex-col justify-center gap-6 px-4 py-10 text-center">
      <div className="flex flex-col items-center gap-3">
        <Logo label={t("logo")} size={56} />
        <h1 className="text-3xl font-semibold tracking-tight">{t("verifyTitle")}</h1>
      </div>
      {state.step === "ready" && (
        <>
          <p className="text-ink-2">{t("verifyIntro")}</p>
          {state.error && (
            <p role="alert" className="text-danger-ink">
              {t(`verifyErrors.${state.error}`)}
            </p>
          )}
          <Button size="lg" disabled={state.sending} onClick={() => void signIn(state.token)}>
            {t("verifySubmit")}
          </Button>
        </>
      )}
      {state.step === "invalid" && (
        <>
          <p role="alert" className="text-danger-ink">
            {t("verifyInvalid")}
          </p>
          <a
            href={`/${locale}/connexion`}
            className="trv-button"
            data-variant="primary"
            data-size="lg"
          >
            {t("verifyResend")}
          </a>
        </>
      )}
    </main>
  );
}
