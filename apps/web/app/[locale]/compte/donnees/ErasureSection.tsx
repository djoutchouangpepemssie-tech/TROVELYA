"use client";

import { Button, Dialog } from "@trovelya/ui";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { apiCall } from "@/lib/api";

import type { StepUp } from "./types";

/**
 * Account erasure (Q10): confirmed, then a strong proof; the member is signed out at once and
 * the account erased after the grace period. Already asked for: the date, and the notice at the
 * top of every page offers to cancel.
 */
export function ErasureSection({
  graceDays,
  eraseAt,
  stepUp,
  onErased,
  onDone,
}: {
  graceDays: number;
  eraseAt: string | null;
  stepUp: StepUp;
  onErased: (eraseAt: string) => void;
  onDone: (message: string) => void;
}) {
  const t = useTranslations("Account.data");
  const format = useFormatter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function erase() {
    setConfirming(false);
    setBusy(true);
    onDone("");
    const result = await stepUp(() =>
      apiCall<{ erase_at: string }>("/v1/me/erasure", { method: "POST" }),
    );
    setBusy(false);
    if (result.ok) onErased(result.data.erase_at);
    else if (!result.code.startsWith("step_up_")) onDone(t("error"));
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
        <p className="font-medium">
          {t("erasurePending", {
            date: format.dateTime(new Date(eraseAt), { dateStyle: "long" }),
          })}
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-2">{t("erasureIntro", { days: graceDays })}</p>
          <p className="text-sm text-ink-2">{t("erasureExportFirst")}</p>
          <Button
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
