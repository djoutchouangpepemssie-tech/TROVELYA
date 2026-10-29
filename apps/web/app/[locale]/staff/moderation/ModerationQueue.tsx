"use client";

import { Badge, Button, Card, EmptyState, Input, Price, Select, Skeleton } from "@trovelya/ui";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { apiCall } from "@/lib/api";
import { pickVariant, type Variant } from "@/lib/media";

type Reason = { code: string; label: string };
type Detection = { part: string | null; action_taken: string };
type Item = {
  id: string;
  title: string;
  description: string;
  category: string;
  price: { amount_minor: number; currency: string };
  submitted_at: string;
  reasons: Reason[];
  reason_text: string | null;
  photos: Variant[][];
  detections: Detection[];
};
type Queue = { items: Item[]; reject_reasons: Reason[] };
type Decided = { status: "active" | "removed" | "withdrawn" };

type State =
  { step: "loading" } | { step: "error"; code: string } | { step: "ready"; queue: Queue };

const OTHER = "other";

/** The listings awaiting moderation, the oldest first: approve, or reject with a reason. */
export function ModerationQueue() {
  const t = useTranslations("StaffModeration");
  const [state, setState] = useState<State>({ step: "loading" });
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await apiCall<Queue>("/v1/staff/moderation/listings");
    if (result.ok) setState({ step: "ready", queue: result.data });
    else
      setState({
        step: "error",
        // A staff session whose passkey proof is too old signs in again, like a signed-out one.
        code:
          result.status === 401 || result.code === "step_up_required"
            ? "unauthenticated"
            : result.status === 403
              ? "forbidden"
              : "unknown",
      });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function decided(item: Item, status: Decided["status"]) {
    setNotice(t(`done.${status}`, { title: item.title }));
    setState((current) =>
      current.step === "ready"
        ? {
            step: "ready",
            queue: { ...current.queue, items: current.queue.items.filter((i) => i.id !== item.id) },
          }
        : current,
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-ink-2">{t("intro")}</p>
      </header>
      <p role="status" className="font-medium">
        {notice}
      </p>
      {state.step === "loading" && (
        <div aria-busy="true" aria-label={t("loading")} className="flex flex-col gap-3">
          <Skeleton height={120} />
          <Skeleton height={120} />
        </div>
      )}
      {state.step === "error" && (
        <p role="alert" className="text-danger-ink">
          {t(`errors.${state.code}`)}
        </p>
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
            onStale={() => void load()}
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
  onDecided: (status: Decided["status"]) => void;
  onStale: () => void;
}) {
  const t = useTranslations("StaffModeration");
  const locale = useLocale();
  const format = useFormatter();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const headingId = `listing-${item.id}`;

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
    const result = await apiCall<Decided>(`/v1/staff/moderation/listings/${item.id}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setSending(false);
    if (result.ok) {
      onDecided(result.data.status);
      return;
    }
    const known = ["invalid_transition", "photo_required", "validation_error"];
    setError(known.includes(result.code) ? result.code : "unknown");
    if (result.code === "invalid_transition") onStale();
  }

  return (
    <Card className="flex flex-col gap-4 p-4">
      <article aria-labelledby={headingId} className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id={headingId} className="text-lg font-semibold">
            {item.title}
          </h2>
          <Price
            amountMinor={item.price.amount_minor}
            currency={item.price.currency}
            locale={locale}
          />
        </div>
        <p className="text-sm text-ink-2">
          {t("submitted", { date: format.dateTime(new Date(item.submitted_at), "short") })}
          {" · "}
          {t("category", { key: item.category })}
        </p>
        <div className="flex gap-2 overflow-x-auto">
          {item.photos.length === 0 && <p className="text-sm text-ink-2">{t("noPhoto")}</p>}
          {item.photos.map((variants, index) => {
            const src = pickVariant(variants, 160);
            return src ? (
              // eslint-disable-next-line @next/next/no-img-element -- variants served as is (ADR-0019)
              <img
                key={src}
                src={src}
                alt={t("photo", { n: index + 1 })}
                width={160}
                height={120}
                className="h-30 w-40 shrink-0 rounded-lg object-cover"
              />
            ) : null;
          })}
        </div>
        <p className="whitespace-pre-line">{item.description}</p>
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-ink-2">{t("why")}</h3>
          <div className="flex flex-wrap gap-2">
            {item.reasons.map((r) => (
              <Badge key={r.code} tone="warning">
                {r.label}
              </Badge>
            ))}
          </div>
          {item.detections.map((d, index) => (
            <p key={index} className="text-sm">
              {t("detection", { part: d.part ?? "other", action: d.action_taken })}
            </p>
          ))}
        </div>
      </article>
      {error && (
        <p role="alert" className="text-danger-ink">
          {t(`errors.${error}`)}
        </p>
      )}
      {rejecting ? (
        <div className="flex flex-col gap-3">
          <Select
            label={t("reason")}
            placeholder={t("reasonPlaceholder")}
            options={reasons.map((r) => ({ value: r.code, label: r.label }))}
            value={reason}
            onValueChange={setReason}
          />
          <Input
            label={t("reasonText")}
            hint={t("reasonTextHint")}
            value={text}
            maxLength={1000}
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" disabled={sending} onClick={() => void decide("reject")}>
              {t("confirmReject")}
            </Button>
            <Button
              variant="ghost"
              disabled={sending}
              onClick={() => {
                setRejecting(false);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button disabled={sending} onClick={() => void decide("approve")}>
            {t("approve")}
          </Button>
          <Button
            variant="secondary"
            disabled={sending}
            onClick={() => {
              setRejecting(true);
            }}
          >
            {t("reject")}
          </Button>
        </div>
      )}
    </Card>
  );
}
