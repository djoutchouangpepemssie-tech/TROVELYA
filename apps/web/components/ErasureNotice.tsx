"use client";

import { Button } from "@trovelya/ui";
import { useFormatter, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiCall } from "@/lib/api";

/**
 * Q10: a member who signs in again during the grace period sees, on every page, when the
 * account will be erased and can cancel in one click.
 */
export function ErasureNotice() {
  const t = useTranslations("ErasureNotice");
  const format = useFormatter();
  const { me, refresh } = useSession();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const status = useRef<HTMLParagraphElement>(null);

  async function cancel() {
    setBusy(true);
    setFailed(false);
    const result = await apiCall<null>("/v1/me/erasure/cancel", { method: "POST" });
    setBusy(false);
    // 409: already cancelled (another tab); the notice goes away all the same.
    if (!result.ok && result.code !== "no_erasure_pending") {
      setFailed(true);
      return;
    }
    setCancelled(true);
    await refresh();
    status.current?.focus();
  }

  if (cancelled) {
    return (
      <div className="border-b border-line bg-surface-2">
        <p
          ref={status}
          role="status"
          tabIndex={-1}
          className="mx-auto max-w-5xl px-4 py-3 text-sm font-medium"
        >
          {t("cancelled")}
        </p>
      </div>
    );
  }
  if (!me?.erase_at) return null;
  return (
    <section aria-label={t("label")} className="border-b border-line bg-surface-2">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-3">
        <p className="text-sm font-medium">
          {t("pending", { date: format.dateTime(new Date(me.erase_at), { dateStyle: "long" }) })}
        </p>
        <Button size="sm" disabled={busy} onClick={() => void cancel()}>
          {t("cancel")}
        </Button>
        {failed && (
          <p role="alert" className="text-sm text-danger-ink">
            {t("error")}
          </p>
        )}
      </div>
    </section>
  );
}
