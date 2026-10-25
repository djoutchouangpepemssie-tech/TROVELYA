"use client";

import { Button, Dialog } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import type { ApiResult } from "@/lib/api";
import { authApi } from "@/lib/auth";
import { type PasskeyError, requestStepUpLink, stepUpWithPasskey } from "@/lib/passkeys";

// Where the confirmation link brings the member back (/fr/confirmer). Local storage: the link
// is usually opened in another tab, from the mail app.
export const STEP_UP_RETURN_KEY = "trv_stepup_return";

type Outcome = "confirmed" | "link_sent" | "cancelled";

/**
 * Sensitive actions (13.2) answer `403 step_up_required` without a recent strong proof.
 * `run(action)` then asks for one (passkey, or a link by e-mail) and, once confirmed with a
 * passkey, does the action again. With the e-mailed link, the member comes back to this page
 * and does it again themselves.
 */
export function useStepUp(): {
  run: <T>(action: () => Promise<ApiResult<T>>) => Promise<ApiResult<T>>;
  dialog: ReactNode;
} {
  const [open, setOpen] = useState(false);
  const settle = useRef<((outcome: Outcome) => void) | null>(null);

  const finish = useCallback((outcome: Outcome) => {
    setOpen(false);
    settle.current?.(outcome);
    settle.current = null;
  }, []);

  const run = useCallback(async <T,>(action: () => Promise<ApiResult<T>>) => {
    // The button that started the action: focus goes back to it once it is usable again.
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = await action();
    if (first.ok || first.code !== "step_up_required") return first;
    const outcome = await new Promise<Outcome>((resolve) => {
      settle.current = resolve;
      setOpen(true);
    });
    if (opener) focusWhenEnabled(opener);
    if (outcome !== "confirmed") {
      return {
        ok: false as const,
        status: 403,
        code: outcome === "link_sent" ? "step_up_pending" : "step_up_cancelled",
      };
    }
    return action();
  }, []);

  return { run, dialog: <StepUpDialog open={open} onFinish={finish} /> };
}

function StepUpDialog({ open, onFinish }: { open: boolean; onFinish: (outcome: Outcome) => void }) {
  const t = useTranslations("StepUp");
  const [passkeys, setPasskeys] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<PasskeyError | null>(null);
  const [linkSent, setLinkSent] = useState(false);

  // Each opening starts clean, and learns whether passkeys are on.
  function onOpenChange(next: boolean) {
    if (next) return;
    onFinish(linkSent ? "link_sent" : "cancelled");
    setError(null);
    setLinkSent(false);
  }
  useEffect(() => {
    if (!open || passkeys !== null) return;
    void authApi.methods().then((methods) => {
      setPasskeys(methods?.passkey ?? false);
    });
  }, [open, passkeys]);

  async function withPasskey() {
    setBusy(true);
    setError(null);
    const result = await stepUpWithPasskey();
    setBusy(false);
    if (result.ok) {
      onFinish("confirmed");
      return;
    }
    setError(result.error);
  }

  async function withLink() {
    setBusy(true);
    setError(null);
    try {
      window.localStorage.setItem(STEP_UP_RETURN_KEY, window.location.pathname);
    } catch {
      // Storage blocked: the confirmation page offers the account page instead.
    }
    const result = await requestStepUpLink();
    setBusy(false);
    if (result.ok) setLinkSent(true);
    else setError(result.error);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("title")}
      description={t("description")}
      closeLabel={t("close")}
    >
      <div className="mt-4 flex flex-col gap-3">
        {linkSent ? (
          <p role="status" className="font-medium">
            {t("linkSent")}
          </p>
        ) : (
          <>
            {passkeys && (
              <Button disabled={busy} onClick={() => void withPasskey()}>
                {t("passkey")}
              </Button>
            )}
            <Button
              variant={passkeys ? "secondary" : "primary"}
              disabled={busy}
              onClick={() => void withLink()}
            >
              {t("link")}
            </Button>
          </>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger-ink">
            {t(`errors.${error}`)}
          </p>
        )}
      </div>
    </Dialog>
  );
}

/** Focus an element as soon as it is enabled again (a button disabled while its action runs). */
function focusWhenEnabled(element: HTMLElement, frames = 30) {
  if (!element.isConnected) return;
  if (!element.matches(":disabled")) {
    element.focus();
    return;
  }
  if (frames > 0) {
    requestAnimationFrame(() => {
      focusWhenEnabled(element, frames - 1);
    });
  }
}
