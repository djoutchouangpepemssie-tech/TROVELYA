"use client";

import { Button, Dialog } from "@trovelya/ui";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiCall } from "@/lib/api";

import type { StepUp } from "./types";

/**
 * Account erasure (Q10): confirmed, then a strong proof; the member is signed out at once and
 * the account erased after the grace period. Already asked for: the date, and the way to
 * cancel (also offered by the notice at the top of every page).
 */
export function ErasureSection({
  graceDays,
  eraseAt,
  stepUp,
  onErased,
  onSignedOut,
  onDone,
}: {
  graceDays: number;
  eraseAt: string | null;
  stepUp: StepUp;
  onErased: (eraseAt: string) => void;
  onSignedOut: () => Promise<void>;
  onDone: (message: string) => void;
}) {
  const t = useTranslations("Account.data");
  const tNotice = useTranslations("ErasureNotice");
  const format = useFormatter();
  const { refresh } = useSession();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const request = useRef<HTMLButtonElement>(null);
  // Focus back on « Supprimer mon compte » once React has drawn it again (enabled, or back
  // after a cancellation): the button that had it is gone with the dialog or the date.
  const [refocus, setRefocus] = useState(0);
  useEffect(() => {
    if (refocus > 0) request.current?.focus();
  }, [refocus]);

  async function erase() {
    setConfirming(false);
    setBusy(true);
    onDone("");
    const result = await stepUp(() =>
      apiCall<{ erase_at: string }>("/v1/me/erasure", { method: "POST" }),
    );
    setBusy(false);
    if (result.ok) {
      onErased(result.data.erase_at);
      return;
    }
    // 401, or an answer lost on the way (the erasure may be recorded and the session closed):
    // the refreshed session tells, and a closed one goes to the sign-in page.
    if (result.status === 401 || result.status === 0) await onSignedOut();
    if (!result.code.startsWith("step_up_")) onDone(t("error"));
    setRefocus((n) => n + 1);
  }

  async function cancel() {
    setBusy(true);
    onDone("");
    const result = await apiCall<null>("/v1/me/erasure/cancel", { method: "POST" });
    setBusy(false);
    if (!result.ok && result.status === 401) {
      await onSignedOut();
      return;
    }
    if (!result.ok && result.code !== "no_erasure_pending") {
      onDone(tNotice("error"));
      return;
    }
    onDone(tNotice("cancelled"));
    await refresh(); // no date any more, here and in the notice
    setRefocus((n) => n + 1);
  }

  return (
    <section
      aria-labelledby="erasure-title"
      className="flex flex-col gap-3 border-t border-line pt-6"
    >
      <h2 id="erasure-title" className="text-xl font-semibold">
        {t("erasureTitle")}
      </h2>
      {eraseAt ? (
        <>
          <p className="font-medium">
            {t("erasurePending", {
              date: format.dateTime(new Date(eraseAt), { dateStyle: "long" }),
            })}
          </p>
          <Button className="self-start" disabled={busy} onClick={() => void cancel()}>
            {t("erasureCancel")}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-ink-2">{t("erasureIntro", { days: graceDays })}</p>
          <p className="text-sm text-ink-2">{t("erasureExportFirst")}</p>
          <Button
            ref={request}
            variant="danger"
            className="self-start"
            disabled={busy}
            onClick={() => {
              setConfirming(true);
            }}
          >
            {t("erasureRequest")}
          </Button>
        </>
      )}
      <Dialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("erasureConfirmTitle")}
        description={t("erasureConfirmText", { days: graceDays })}
        closeLabel={t("close")}
      >
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setConfirming(false);
            }}
          >
            {t("cancel")}
          </Button>
          <Button variant="danger" onClick={() => void erase()}>
            {t("erasureConfirm")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
