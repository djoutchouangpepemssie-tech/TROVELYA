"use client";

import { Button } from "@trovelya/ui";
import { useFormatter, useTranslations } from "next-intl";

import { apiCall, apiFetch, type ApiResult } from "@/lib/api";

import type { DataRequest, StepUp } from "./types";

/** GDPR export (ADR-0016): ask for the archive, then download it while it is kept. */
export function ExportSection({
  requests,
  stepUp,
  onChanged,
  onDone,
}: {
  requests: DataRequest[];
  stepUp: StepUp;
  onChanged: () => Promise<void>;
  onDone: (message: string) => void;
}) {
  const t = useTranslations("Account.data");
  const format = useFormatter();
  const exports = requests.filter((request) => request.kind === "export");
  const pending = exports.find((request) => ["received", "processing"].includes(request.status));
  const day = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "long" });

  async function ask() {
    onDone("");
    const result = await stepUp(() =>
      apiCall<{ request_id: string }>("/v1/me/data-export", { method: "POST" }),
    );
    if (result.ok) {
      onDone(t("exportRequested"));
      await onChanged();
    } else if (!result.code.startsWith("step_up_")) onDone(t("error"));
  }

  async function download(request: DataRequest) {
    onDone("");
    const result = await stepUp(() => archive(request.id));
    if (result.ok) {
      save(result.data, `trovelya-export-${request.created_at.slice(0, 10)}.zip`);
      onDone(t("downloaded"));
    } else if (result.status === 404) {
      onDone(t("error"));
      await onChanged(); // expired in the meantime: the list says so
    } else if (!result.code.startsWith("step_up_")) onDone(t("error"));
  }

  function line(request: DataRequest): string {
    const date = day(request.created_at);
    if (request.status === "refused") return t("exportRefused", { date });
    if (request.status !== "completed") return t("exportPending", { date });
    if (!request.expires_at || new Date(request.expires_at) <= new Date()) {
      return t("exportExpired", { date });
    }
    return t("exportReady", { date, until: day(request.expires_at) });
  }

  const downloadable = (request: DataRequest) =>
    request.status === "completed" &&
    request.expires_at !== null &&
    new Date(request.expires_at) > new Date();

  return (
    <section aria-labelledby="export-title" className="flex flex-col gap-3">
      <h2 id="export-title" className="text-xl font-semibold">
        {t("exportTitle")}
      </h2>
      <p className="text-sm text-ink-2">{t("exportIntro")}</p>
      {exports.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {exports.map((request) => (
            <li key={request.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <p className="text-sm">{line(request)}</p>
              {downloadable(request) && (
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={t("downloadLabel", { date: day(request.created_at) })}
                  onClick={() => void download(request)}
                >
                  {t("download")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!pending && (
        <Button variant="secondary" className="self-start" onClick={() => void ask()}>
          {t("exportRequest")}
        </Button>
      )}
    </section>
  );
}

/** The archive, through the relay (a strong sign-in is needed, as for the request). */
async function archive(id: string): Promise<ApiResult<Blob>> {
  try {
    const response = await apiFetch(`/v1/me/data-export/${id}/download`);
    if (response.ok) return { ok: true, data: await response.blob() };
    const body = (await response.json().catch(() => ({}))) as { code?: string };
    return { ok: false, status: response.status, code: body.code ?? "unknown" };
  } catch {
    return { ok: false, status: 0, code: "network" };
  }
}

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Let the browser start the download before the address is released.
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 60_000);
}
