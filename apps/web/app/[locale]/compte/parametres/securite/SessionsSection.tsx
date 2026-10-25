"use client";

import { Badge, Button } from "@trovelya/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiCall } from "@/lib/api";

type Session = {
  id: string;
  current: boolean;
  created_at: string;
  last_used_at: string;
  device_label: string | null;
  country_code: string | null;
};

/** Devices where the account is open; revoke one, or every other one. */
export function SessionsSection({ onDone }: { onDone: (message: string) => void }) {
  const t = useTranslations("Account.security.sessions");
  const tAccount = useTranslations("Account");
  const format = useFormatter();
  const locale = useLocale();
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    const result = await apiCall<{ data: Session[] }>("/v1/me/sessions");
    if (result.ok) setSessions(result.data.data);
    else setLoadFailed(true);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Back on this tab after signing in elsewhere: the list shows the new device.
  useEffect(() => {
    function refresh() {
      if (document.visibilityState === "visible") void load();
    }
    document.addEventListener("visibilitychange", refresh);
    return () => {
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  async function revoke(path: `/v1/${string}`, message: string) {
    setBusy(true);
    setFailed(false);
    onDone("");
    const result = await apiCall<null>(path, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) {
      setFailed(true);
      return;
    }
    onDone(message);
    await load();
    // The button pressed is gone with its row: focus goes to the section title.
    heading.current?.focus();
  }

  function country(code: string | null): string | null {
    if (!code) return null;
    try {
      return new Intl.DisplayNames([locale], { type: "region" }).of(code) ?? code;
    } catch {
      return code;
    }
  }

  const others = sessions?.filter((session) => !session.current) ?? [];

  return (
    <section
      aria-labelledby="sessions-title"
      className="flex flex-col gap-3 border-t border-line pt-6"
    >
      <h2 id="sessions-title" ref={heading} tabIndex={-1} className="text-xl font-semibold">
        {t("title")}
      </h2>
      <p className="text-sm text-ink-2">{t("intro")}</p>
      {loadFailed && (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-danger-ink">{t("loadError")}</p>
          <Button variant="secondary" onClick={() => void load()}>
            {tAccount("retry")}
          </Button>
        </div>
      )}
      {sessions && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {sessions.map((session) => {
            const device = session.device_label ?? t("unknownDevice");
            const place = country(session.country_code);
            return (
              <li key={session.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    <span className="truncate">{place ? `${device} · ${place}` : device}</span>
                    {session.current && <Badge tone="brand">{t("current")}</Badge>}
                  </p>
                  <p className="text-sm text-ink-2">
                    {t("lastUsed", {
                      date: format.dateTime(new Date(session.last_used_at), {
                        dateStyle: "medium",
                        timeStyle: "short",
                      }),
                    })}
                  </p>
                </div>
                {!session.current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    aria-label={t("revokeLabel", { device })}
                    onClick={() => void revoke(`/v1/me/sessions/${session.id}`, t("revoked"))}
                  >
                    {t("revoke")}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {others.length > 0 && (
        <Button
          variant="secondary"
          disabled={busy}
          className="self-start"
          onClick={() => void revoke("/v1/me/sessions", t("revokedOthers"))}
        >
          {t("revokeOthers")}
        </Button>
      )}
      {failed && (
        <p role="alert" className="text-sm text-danger-ink">
          {t("error")}
        </p>
      )}
    </section>
  );
}
