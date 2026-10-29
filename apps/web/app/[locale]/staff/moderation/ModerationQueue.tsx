"use client";

import { Badge, Button, Card, EmptyState, Input, Price, Select, Skeleton } from "@trovelya/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiCall } from "@/lib/api";
import { pickVariant, type Variant } from "@/lib/media";

type Reason = { code: string; label: string };
type Detection = { part: string | null; signals: string[]; action_taken: string };
type Item = {
  id: string;
  title: string;
  description: string;
  category_name: string;
  price: { amount_minor: number; currency: string };
  submitted_at: string;
  reasons: Reason[];
  reason_text: string | null;
  photos: Variant[][];
  detections: Detection[];
};
type Queue = { items: Item[]; reject_reasons: Reason[] };
type Status = "active" | "removed" | "withdrawn";

type State =
  | { step: "loading" }
  | { step: "error"; code: "unauthenticated" | "forbidden" | "load" }
  | { step: "ready"; queue: Queue };

const OTHER = "other";
// Answers meaning the card no longer reflects the listing: the queue is read again.
const STALE = new Set(["invalid_transition", "not_found"]);
const KNOWN = new Set([...STALE, "photo_required", "validation_error", "network"]);

/** The listings awaiting moderation, the oldest first: approve, or reject with a reason. */
export function ModerationQueue() {
  const t = useTranslations("StaffModeration");
  const [state, setState] = useState<State>({ step: "loading" });
  const [notice, setNotice] = useState("");
  const title = useRef<HTMLHeadingElement>(null);
  const latest = useRef(0); // a reply to an older reading never overwrites a newer one

  const load = useCallback(async () => {
    const reading = ++latest.current;
    const result = await apiCall<Queue>("/v1/staff/moderation/listings");
    if (reading !== latest.current) return;
    if (result.ok) {
      setState({ step: "ready", queue: result.data });
      return;
    }
    // A staff session whose passkey proof is too old signs in again, like a signed-out one.
    const signIn = result.status === 401 || result.code === "step_up_required";
    const code = signIn ? "unauthenticated" : result.status === 403 ? "forbidden" : "load";
    setState({ step: "error", code });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Said in the status region (emptied first: the same sentence twice is still announced). */
  function announce(message: string) {
    setNotice("");
    setTimeout(() => {
      setNotice(message);
    }, 50);
    title.current?.focus(); // the card is gone: the keyboard starts again from the heading
  }

  function decided(item: Item, status: Status) {
    announce(t(`done.${status}`, { title: item.title }));
    if (state.step !== "ready") return;
    const items = state.queue.items.filter((i) => i.id !== item.id);
    setState({ step: "ready", queue: { ...state.queue, items } });
    if (items.length === 0) void load(); // more may wait beyond the page read
  }

  function stale(code: string) {
    announce(t(`errors.${code}`));
    void load();
  }

  return (
    <main
      className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-8"
      aria-busy={state.step === "loading"}
    >
      <header className="flex flex-col gap-2">
        <h1 ref={title} tabIndex={-1} className="text-2xl font-semibold outline-none">
          {t("title")}
        </h1>
        <p className="text-ink-2">{t("intro")}</p>
      </header>
      <p role="status" className="font-medium">
        {state.step === "loading" ? <span className="sr-only">{t("loading")}</span> : notice}
      </p>
      {state.step === "loading" && (
        <div className="flex flex-col gap-3">
          <Skeleton height={120} />
          <Skeleton height={120} />
        </div>
      )}
      {state.step === "error" && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-danger-ink">
            {t(`errors.${state.code}`)}
          </p>
          {state.code === "load" && (
            <Button variant="secondary" onClick={() => void load()}>
              {t("reload")}
            </Button>
          )}
        </div>
      )}
      {state.step === "ready" && state.queue.items.length === 0 && (
        <EmptyState
          title={t("empty")}
          description={t("emptyHint")}
          action={
            <Button variant="secondary" onClick={() => void load()}>
              {t("reload")}
            </Button>
          }
        />
      )}
      {state.step === "ready" &&
        state.queue.items.map((item) => (
          <ReviewCard
            key={item.id}
            item={item}
            reasons={state.queue.reject_reasons}
            onDecided={(status) => {
              decided(item, status);
            }}
            onStale={stale}
          />
        ))}
    </main>
  );
}

function ReviewCard({
  item,
  reasons,
  onDecided,
  onStale,
}: {
  item: Item;
  reasons: Reason[];
  onDecided: (status: Status) => void;
  onStale: (code: string) => void;
}) {
  const t = useTranslations("StaffModeration");
  const locale = useLocale();
  const format = useFormatter();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const form = useRef<HTMLDivElement>(null);
  const rejectButton = useRef<HTMLButtonElement>(null);
  const headingId = `listing-${item.id}`;

  useEffect(() => {
    if (rejecting) form.current?.querySelector<HTMLElement>("[role=combobox]")?.focus();
  }, [rejecting]);

  function cancel() {
    setRejecting(false);
    setReason("");
    setText("");
    setError(null);
    setTimeout(() => rejectButton.current?.focus(), 0);
  }

  async function decide(action: "approve" | "reject") {
    if (action === "reject" && !reason) {
      setError("reason_required");
      return;
    }
    if (action === "reject" && reason === OTHER && !text.trim()) {
      setError("text_required");
      return;
    }
    setSending(true);
    setError(null);
    const body =
      action === "reject" ? { reason_code: reason, reason_text: text.trim() || null } : {};
    const result = await apiCall<{ status: Status }>(
      `/v1/staff/moderation/listings/${item.id}/${action}`,
      { method: "POST", body: JSON.stringify(body) },
    );
    setSending(false);
    if (result.ok) {
      onDecided(result.data.status);
      return;
    }
    if (STALE.has(result.code)) {
      onStale(result.code);
      return;
    }
    if (result.code === "step_up_required") setError("unauthenticated");
    else if (result.status === 403) setError("own_listing");
    else setError(KNOWN.has(result.code) ? result.code : "unknown");
  }

  const fieldError = (code: string) => (error === code ? { error: t(`errors.${code}`) } : {});
  const serverError = error && !["reason_required", "text_required"].includes(error);
  const signal = (s: string) => (t.has(`signals.${s}`) ? t(`signals.${s}`) : s);

  return (
    <Card className="p-4">
      <article aria-labelledby={headingId} className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id={headingId} className="min-w-0 text-lg font-semibold [overflow-wrap:anywhere]">
            {item.title}
          </h2>
          <Price
            amountMinor={item.price.amount_minor}
            currency={item.price.currency}
            locale={locale}
          />
        </div>
        <p className="text-sm text-ink-2">
          {t("submitted", {
            date: format.dateTime(new Date(item.submitted_at), {
              dateStyle: "short",
              timeStyle: "short",
            }),
          })}
          {" · "}
          {t("category", { name: item.category_name })}
        </p>
        {item.photos.length === 0 ? (
          <p className="text-sm text-ink-2">{t("noPhoto")}</p>
        ) : (
          <ul aria-label={t("photos")} className="flex flex-wrap gap-2">
            {item.photos.map((variants, index) => {
              const src = pickVariant(variants, 160);
              return src ? (
                <li key={index}>
                  <a href={pickVariant(variants, 2000)} target="_blank" rel="noreferrer">
                    {/* eslint-disable-next-line @next/next/no-img-element -- variants as is (ADR-0019) */}
                    <img
                      src={src}
                      alt={t("photo", { n: index + 1 })}
                      width={160}
                      height={120}
                      className="h-30 w-40 rounded-lg object-cover"
                    />
                  </a>
                </li>
              ) : null;
            })}
          </ul>
        )}
        <p className="whitespace-pre-line [overflow-wrap:anywhere]">{item.description}</p>
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-ink-2">{t("why")}</h3>
          <div className="flex flex-wrap gap-2">
            {item.reasons.map((r) => (
              <Badge key={r.code} tone="warning">
                {r.label}
              </Badge>
            ))}
          </div>
          {item.reason_text && item.reason_text !== item.reasons[0]?.label && (
            <p className="text-sm [overflow-wrap:anywhere]">{item.reason_text}</p>
          )}
          {item.detections.map((d, index) => (
            <p key={index} className="text-sm">
              {t("detection", {
                signals: d.signals.map(signal).join(", "),
                part: d.part ?? "other",
                action: d.action_taken,
              })}
            </p>
          ))}
        </div>
        {serverError && (
          <p role="alert" className="text-danger-ink">
            {t(`errors.${error}`)}
          </p>
        )}
        {rejecting ? (
          <div ref={form} className="flex flex-col gap-3">
            <Select
              label={t("reason")}
              placeholder={t("reasonPlaceholder")}
              options={reasons.map((r) => ({ value: r.code, label: r.label }))}
              value={reason}
              onValueChange={(value) => {
                setReason(value);
                setError(null);
              }}
              {...fieldError("reason_required")}
            />
            <Input
              label={t("reasonText")}
              hint={t("reasonTextHint")}
              value={text}
              maxLength={1000}
              disabled={sending}
              onChange={(event) => {
                setText(event.target.value);
                setError(null);
              }}
              {...fieldError("text_required")}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                disabled={sending}
                aria-describedby={headingId}
                onClick={() => void decide("reject")}
              >
                {t("confirmReject")}
              </Button>
              <Button variant="ghost" disabled={sending} onClick={cancel}>
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={sending}
              aria-describedby={headingId}
              onClick={() => void decide("approve")}
            >
              {t("approve")}
            </Button>
            <Button
              ref={rejectButton}
              variant="secondary"
              disabled={sending}
              aria-describedby={headingId}
              onClick={() => {
                setRejecting(true);
              }}
            >
              {t("reject")}
            </Button>
          </div>
        )}
      </article>
    </Card>
  );
}
