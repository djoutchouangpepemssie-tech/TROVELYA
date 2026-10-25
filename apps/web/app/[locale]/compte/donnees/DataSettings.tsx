"use client";

import { Button } from "@trovelya/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { useStepUp } from "@/components/StepUp";
import { apiCall } from "@/lib/api";

import { AccountShell } from "../AccountShell";
import { ErasureSection } from "./ErasureSection";
import { ExportSection } from "./ExportSection";
import type { DataRequests } from "./types";

/** One status line and one step-up dialog for the page; the erasure ends on its own screen. */
export function DataSettings() {
  const t = useTranslations("Account.data");
  const tAccount = useTranslations("Account");
  const { me, refresh } = useSession();
  const [requests, setRequests] = useState<DataRequests | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [notice, setNotice] = useState("");
  const [erased, setErased] = useState<string | null>(null);
  const stepUp = useStepUp();

  // Loads overlap (opening, back on the tab, after a request): only the latest one is shown.
  const latest = useRef(0);
  const load = useCallback(async () => {
    const call = ++latest.current;
    setLoadFailed(false);
    const result = await apiCall<DataRequests>("/v1/me/data-requests");
    if (call !== latest.current) return;
    if (result.ok) setRequests(result.data);
    else if (result.status === 401)
      await refresh(); // signed out elsewhere: to the sign-in page
    else setLoadFailed(true);
  }, [refresh]);

  useEffect(() => {
    void load();
  }, [load]);

  // Back from the mail app once the export is ready: the list shows it.
  useEffect(() => {
    function reload() {
      if (document.visibilityState === "visible") void load();
    }
    document.addEventListener("visibilitychange", reload);
    return () => {
      document.removeEventListener("visibilitychange", reload);
    };
  }, [load]);

  // The server closed every session: the header shows the visitor as signed out.
  useEffect(() => {
    if (erased) void refresh();
  }, [erased, refresh]);

  // No account frame once erased: it would send the signed-out visitor to the sign-in page.
  if (erased) return <ErasureRequested eraseAt={erased} />;

  return (
    <AccountShell title={t("title")}>
      {loadFailed && (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-danger-ink">{t("loadError")}</p>
          <Button variant="secondary" onClick={() => void load()}>
            {tAccount("retry")}
          </Button>
        </div>
      )}
      {requests && (
        <>
          <ExportSection
            requests={requests.data}
            stepUp={stepUp.run}
            onChanged={load}
            onSignedOut={refresh}
            onDone={setNotice}
          />
          <ErasureSection
            graceDays={requests.erasure_grace_days}
            eraseAt={me?.erase_at ?? null}
            stepUp={stepUp.run}
            onErased={setErased}
            onSignedOut={refresh}
            onDone={setNotice}
          />
        </>
      )}
      {stepUp.dialog}
      <div role="status" className="sticky bottom-20 md:bottom-4">
        {notice && (
          <p className="rounded-lg bg-ink px-4 py-3 text-sm font-medium text-surface shadow-lg">
            {notice}
          </p>
        )}
      </div>
    </AccountShell>
  );
}

function ErasureRequested({ eraseAt }: { eraseAt: string }) {
  const t = useTranslations("Account.data");
  const format = useFormatter();
  const locale = useLocale();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-4 px-4 py-10">
      <h1 ref={heading} tabIndex={-1} className="text-3xl font-semibold tracking-tight">
        {t("erasureDoneTitle")}
      </h1>
      <p role="status">
        {t("erasureDone", { date: format.dateTime(new Date(eraseAt), { dateStyle: "long" }) })}
      </p>
      <p className="text-ink-2">{t("erasureDoneCancel")}</p>
      <a href={`/${locale}`} className="trv-button self-start" data-variant="primary">
        {t("home")}
      </a>
    </main>
  );
}
