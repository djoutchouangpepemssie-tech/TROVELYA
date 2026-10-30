"use client";

import { Button, IconButton } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useEffect, useReducer, useRef, useState } from "react";

import { uploadPhoto } from "@/lib/media";
import { MAX_PHOTOS, photos, type SellPhoto } from "@/lib/sell/photos";

import { SellStep } from "./SellStep";

// Plan P2-T09a: what a phone camera or gallery gives (the API checks the file again).
const ACCEPT = "image/jpeg,image/png,image/webp";
// Two at a time: the first photo is ready sooner on a phone network (the AI starts from it).
const PARALLEL = 2;

type Control = "start" | "end" | "remove";

/**
 * W09, step 1 (P2-T09a1): photos taken or chosen, sent two at a time and processed, each
 * change said aloud by the photo's position; the member orders them (the first is the main
 * photo) and takes some away, by keyboard too: the focus stays on the photo moved, or goes to
 * the next one after a removal. The step ends once at least one photo is ready and none is
 * still on its way.
 */
export function PhotoStep({ onDone }: { onDone: (ready: SellPhoto[]) => void }) {
  const t = useTranslations("Sell.photos");
  const [list, dispatch] = useReducer(photos, []);
  const [said, setSaid] = useState({ text: "", count: 0 });
  const [focus, setFocus] = useState<{ key: string; control: Control } | "gallery" | null>(null);
  const current = useRef(list);
  current.current = list;
  const uploads = useRef(new Map<string, AbortController>());
  const previews = useRef(new Map<string, string>());
  const queue = useRef<{ key: string; file: File }[]>([]);
  const active = useRef(0);
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const galleryButton = useRef<HTMLButtonElement>(null);
  const cards = useRef<HTMLOListElement>(null);

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

  useEffect(() => {
    if (focus === null) return;
    if (focus === "gallery") galleryButton.current?.focus();
    else {
      const opposite = focus.control === "start" ? "end" : "start";
      const find = (control: Control) =>
        cards.current?.querySelector<HTMLButtonElement>(
          `[data-photo="${focus.key}"][data-control="${control}"]:not(:disabled)`,
        );
      (find(focus.control) ?? find(opposite) ?? galleryButton.current)?.focus();
    }
    setFocus(null);
  }, [focus, list]);

  function say(text: string) {
    setSaid((last) => ({ text, count: last.count + 1 }));
  }

  function position(key: string): number {
    return current.current.findIndex((photo) => photo.key === key) + 1;
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
      say(t("ready", { position: position(key) }));
    } else {
      dispatch({ type: "failed", key, reason: result.reason });
      say(t("refused", { position: position(key), reason: t(`failure.${result.reason}`) }));
    }
  }

  function pump() {
    while (active.current < PARALLEL && queue.current.length > 0) {
      const next = queue.current.shift();
      if (!next) return;
      active.current += 1;
      void send(next.key, next.file).finally(() => {
        active.current -= 1;
        pump();
      });
    }
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? []);
    event.target.value = ""; // the same file may be chosen again
    const files = chosen.slice(0, MAX_PHOTOS - list.length);
    const added = files.map((file) => {
      const key = crypto.randomUUID();
      const preview = URL.createObjectURL(file);
      previews.current.set(key, preview);
      return { key, file, name: file.name, preview };
    });
    dispatch({ type: "add", photos: added });
    if (chosen.length > files.length) {
      say(t("dropped", { count: chosen.length - files.length, max: MAX_PHOTOS }));
    }
    queue.current.push(...added);
    pump();
  }

  function move(key: string, by: -1 | 1, control: Control) {
    const to = position(key) + by;
    dispatch({ type: "move", key, by });
    setFocus({ key, control });
    say(t("moved", { position: to, count: list.length }));
  }

  function remove(key: string) {
    const index = position(key) - 1;
    const neighbour = list[index + 1] ?? list[index - 1];
    queue.current = queue.current.filter((waiting) => waiting.key !== key);
    uploads.current.get(key)?.abort();
    const preview = previews.current.get(key);
    if (preview) URL.revokeObjectURL(preview);
    previews.current.delete(key);
    dispatch({ type: "remove", key });
    setFocus(neighbour ? { key: neighbour.key, control: "remove" } : "gallery");
    say(t("removed", { count: list.length - 1 }));
  }

  const ready = list.filter((photo) => photo.status === "ready");
  const busy = list.some((photo) => photo.status === "sending" || photo.status === "processing");
  const full = list.length >= MAX_PHOTOS;
  const input = (ref: typeof camera, withCamera: boolean) => (
    <input
      ref={ref}
      type="file"
      accept={ACCEPT}
      {...(withCamera ? { capture: "environment" as const } : { multiple: true })}
      className="sr-only"
      tabIndex={-1}
      aria-hidden="true"
      onChange={choose}
    />
  );

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
      {input(camera, true)}
      {input(gallery, false)}
      <div className="flex flex-wrap gap-2.5">
        <Button disabled={full} onClick={() => camera.current?.click()}>
          {t("camera")}
        </Button>
        <Button
          ref={galleryButton}
          variant="secondary"
          disabled={full}
          onClick={() => gallery.current?.click()}
        >
          {t("gallery")}
        </Button>
      </div>
      <p className="mt-3 text-sm text-ink-2">
        {full
          ? t("full", { max: MAX_PHOTOS })
          : t("count", { count: list.length, max: MAX_PHOTOS })}
      </p>
      <p aria-live="polite" className="sr-only">
        {said.text}
        {said.count % 2 ? " " : ""}
      </p>
      <ol
        ref={cards}
        aria-label={t("title")}
        className="mt-4 grid grid-cols-1 gap-3 min-[380px]:grid-cols-2 sm:grid-cols-3"
      >
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
            <div className="flex flex-wrap gap-1">
              {(["start", "end"] as const).map((control) => (
                <IconButton
                  key={control}
                  variant="secondary"
                  data-photo={photo.key}
                  data-control={control}
                  disabled={control === "start" ? index === 0 : index === list.length - 1}
                  label={t(control, { position: index + 1 })}
                  icon={control === "start" ? "↑" : "↓"}
                  onClick={() => {
                    move(photo.key, control === "start" ? -1 : 1, control);
                  }}
                />
              ))}
              <IconButton
                variant="secondary"
                data-photo={photo.key}
                data-control="remove"
                label={t("remove", { position: index + 1 })}
                icon="✕"
                onClick={() => {
                  remove(photo.key);
                }}
              />
            </div>
          </li>
        ))}
      </ol>
    </SellStep>
  );
}
