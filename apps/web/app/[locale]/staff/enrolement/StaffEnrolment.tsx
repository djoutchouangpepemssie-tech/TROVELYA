"use client";

import { Button } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { enrolStaffPasskey, type PasskeyError } from "@/lib/passkeys";

type State =
  | { step: "reading" }
  | { step: "missing" }
  | { step: "ready"; token: string; error: PasskeyError | null; sending: boolean }
  | { step: "done" };

export function StaffEnrolment() {
  const t = useTranslations("StaffEnrolment");
  const [state, setState] = useState<State>({ step: "reading" });

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    // The token never stays in the address bar or the browser history.
    window.history.replaceState(null, "", window.location.pathname);
    setState(token ? { step: "ready", token, error: null, sending: false } : { step: "missing" });
  }, []);

  async function enrol(token: string) {
    setState({ step: "ready", token, error: null, sending: true });
    const result = await enrolStaffPasskey(token);
    setState(
      result.ok ? { step: "done" } : { step: "ready", token, error: result.error, sending: false },
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-5 px-4">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {state.step === "reading" && <p className="text-ink-2">{t("loading")}</p>}
      {state.step === "missing" && (
        <p role="alert" className="text-danger-ink">
          {t("errors.link_invalid")}
        </p>
      )}
      {state.step === "ready" && (
        <>
          <p className="text-ink-2">{t("intro")}</p>
          {state.error && (
            <p role="alert" className="text-danger-ink">
              {t(`errors.${state.error}`)}
            </p>
          )}
          <Button size="lg" disabled={state.sending} onClick={() => void enrol(state.token)}>
            {t("create")}
          </Button>
        </>
      )}
      {state.step === "done" && (
        <p role="status" className="font-medium">
          {t("done")}
        </p>
      )}
    </main>
  );
}
