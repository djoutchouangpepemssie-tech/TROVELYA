"use client";

import { Button } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useEffect, useReducer, useRef, useState } from "react";

import { uploadPhoto } from "@/lib/media";
import { MAX_PHOTOS, photos, type SellPhoto } from "@/lib/sell/photos";

import { SellStep } from "./SellStep";

// Plan P2-T09a: what a phone camera or gallery gives (the API checks the file again).
const ACCEPT = "image/jpeg,image/png,image/webp";

/**
 * W09, step 1 (P2-T09a1): photos taken or chosen, each sent and processed in turn with its
 * state said aloud; the member orders them (the first is the main photo) and takes some away.
 * The step ends once every photo is either ready or refused, with at least one ready.
 */
export function PhotoStep({ onDone }: { onDone: (ready: SellPhoto[]) => void }) {
  const t = useTranslations("Sell.photos");
  const [list, dispatch] = useReducer(photos, []);
  const [announce, setAnnounce] = useState("");
  const uploads = useRef(new Map<string, AbortController>());
  const previews = useRef(new Map<string, string>());

  useEffect(() => {
    const sending = uploads.current;
    const shown = previews.current;
    return () => {
      sending.forEach((controller) => {
        controller.abort();
      });
      shown.forEach((url) => {
        URL.revokeObjectURL(url);
      });
    };
  }, []);

  function say(name: string, status: SellPhoto["status"]) {
    setAnnounce(t("announce", { name, status: t(`status.${status}`) }));
  }

  async function send(key: string, file: File) {
    const controller = new AbortController();
    uploads.current.set(key, controller);
    const result = await uploadPhoto(file, "listing", undefined, controller.signal, () => {
      dispatch({ type: "processing", key });
    });
    uploads.current.delete(key);
    if (controller.signal.aborted) return;
    if (result.ok) {
      dispatch({ type: "ready", key, media: result.media });
      say(file.name, "ready");
    } else {
      dispatch({ type: "failed", key, reason: result.reason });
      say(file.name, "failed");
    }
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []).slice(0, MAX_PHOTOS - list.length);
    event.target.value = ""; // the same file may be chosen again
    const added = files.map((file) => {
      const key = crypto.randomUUID();
      const preview = URL.createObjectURL(file);
      previews.current.set(key, preview);
      return { key, file, preview };
    });
    dispatch({
      type: "add",
      photos: added.map(({ key, file, preview }) => ({ key, name: file.name, preview })),
    });
    for (const { key, file } of added) void send(key, file);
  }

  function remove(key: string) {
    uploads.current.get(key)?.abort();
    uploads.current.delete(key);
    const preview = previews.current.get(key);
    if (preview) URL.revokeObjectURL(preview);
    previews.current.delete(key);
    dispatch({ type: "remove", key });
  }

  const ready = list.filter((photo) => photo.status === "ready");
  const busy = list.some((photo) => photo.status === "sending" || photo.status === "processing");
  const full = list.length >= MAX_PHOTOS;

  return (
    <SellStep
      step={1}
      title={t("title")}
      intro={t("intro", { max: MAX_PHOTOS })}
      actions={
        <>
          {busy ? <p className="text-sm text-ink-2">{t("waiting")}</p> : null}
          <Button
            disabled={busy || ready.length === 0}
            onClick={() => {
              onDone(ready);
            }}
          >
            {t("next")}
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap gap-2.5">
        <label className="trv-button" data-variant="primary" aria-disabled={full}>
          {t("camera")}
          <input
            type="file"
            accept={ACCEPT}
            capture="environment"
            className="sr-only"
            disabled={full}
            onChange={choose}
          />
        </label>
        <label className="trv-button" data-variant="secondary" aria-disabled={full}>
          {t("gallery")}
          <input
            type="file"
            accept={ACCEPT}
            multiple
            className="sr-only"
            disabled={full}
            onChange={choose}
          />
        </label>
      </div>
      <p className="mt-3 text-sm text-ink-2">
        {full
          ? t("full", { max: MAX_PHOTOS })
          : t("count", { count: list.length, max: MAX_PHOTOS })}
      </p>
      <p aria-live="polite" className="sr-only">
        {announce}
      </p>
      <ol aria-label={t("title")} className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {list.map((photo, index) => (
          <li key={photo.key} className="flex flex-col gap-1.5 rounded-md border border-line p-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- the local file (blob:), as is */}
            <img
              src={photo.preview}
              alt={t("label", { position: index + 1, name: photo.name })}
              className="aspect-square w-full rounded-sm object-cover"
            />
            <p className="text-sm">
              {index === 0 ? <strong>{t("main")} · </strong> : null}
              {t(`status.${photo.status}`)}
            </p>
            {photo.failure ? (
              <p className="text-sm text-danger-ink">{t(`failure.${photo.failure}`)}</p>
            ) : null}
            <div className="flex gap-1">
              <Button
                variant="secondary"
                disabled={index === 0}
                aria-label={t("up", { position: index + 1 })}
                onClick={() => {
                  dispatch({ type: "move", key: photo.key, by: -1 });
                }}
              >
                ↑
              </Button>
              <Button
                variant="secondary"
                disabled={index === list.length - 1}
                aria-label={t("down", { position: index + 1 })}
                onClick={() => {
                  dispatch({ type: "move", key: photo.key, by: 1 });
                }}
              >
                ↓
              </Button>
              <Button
                variant="secondary"
                aria-label={t("remove", { position: index + 1 })}
                onClick={() => {
                  remove(photo.key);
                }}
              >
                ✕
              </Button>
            </div>
          </li>
        ))}
      </ol>
    </SellStep>
  );
}
