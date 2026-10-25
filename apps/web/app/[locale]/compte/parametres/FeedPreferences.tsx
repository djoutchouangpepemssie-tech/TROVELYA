"use client";

import { Button, Switch } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiCall, apiFetch, prepareCsrf } from "@/lib/api";

import type { Preferences } from "../../bienvenue/api";

const DEBOUNCE_MS = 600;

/**
 * The feed preferences of W20: personalised feed and the share of discovery (0 to 100).
 * Preferences are replaced as a whole (PUT), so one request at a time, always with the latest
 * choices: two quick changes cannot overwrite each other, and a failure reloads what is stored.
 */
export function FeedPreferences({ onSaved }: { onSaved: (message: string) => void }) {
  const t = useTranslations("Account.feed");
  const tAccount = useTranslations("Account");
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [failed, setFailed] = useState(false);
  // What the screen shows (local choices included), and the save loop's state.
  const wanted = useRef<Preferences | null>(null);
  const saving = useRef(false);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const announce = useRef(onSaved);
  const savedLabel = t("saved");

  useEffect(() => {
    announce.current = onSaved;
  }, [onSaved]);

  const load = useCallback(async () => {
    setLoadFailed(false);
    const result = await apiCall<Preferences>("/v1/me/preferences");
    if (!result.ok) {
      setLoadFailed(true);
      return;
    }
    wanted.current = result.data;
    setPreferences(result.data);
  }, []);

  const flush = useCallback(async () => {
    if (saving.current || !dirty.current) return;
    saving.current = true;
    // Read through a function: the refs change while a request is in flight.
    const more = () => dirty.current;
    do {
      dirty.current = false;
      const result = await apiCall<Preferences>("/v1/me/preferences", {
        method: "PUT",
        body: JSON.stringify(wanted.current),
      });
      if (!result.ok) {
        saving.current = false;
        dirty.current = false;
        setFailed(true);
        // Show what is really stored rather than a choice that was not saved.
        await load();
        return;
      }
    } while (more());
    saving.current = false;
    announce.current(savedLabel);
  }, [load, savedLabel]);

  useEffect(() => {
    void load();
  }, [load]);

  // Leaving with the slider still settling: send it now rather than lose it. A link inside the
  // app unmounts this component; a full page load or a closed tab only fires `pagehide`, where
  // a `keepalive` request still goes out.
  useEffect(() => {
    function sendNow() {
      if (!timer.current || !wanted.current) return;
      clearTimeout(timer.current);
      timer.current = null;
      void apiFetch("/v1/me/preferences", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(wanted.current),
        keepalive: true,
      });
    }
    window.addEventListener("pagehide", sendNow);
    return () => {
      window.removeEventListener("pagehide", sendNow);
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
        void flush();
      }
    };
  }, [flush]);

  function change(changes: Partial<Preferences>, debounce: boolean) {
    if (!wanted.current) return;
    wanted.current = { ...wanted.current, ...changes };
    setPreferences(wanted.current);
    dirty.current = true;
    setFailed(false);
    onSaved("");
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (debounce) {
      void prepareCsrf(); // Ready in case the page closes before the save.
      timer.current = setTimeout(() => {
        timer.current = null;
        void flush();
      }, DEBOUNCE_MS);
    } else {
      void flush();
    }
  }

  return (
    <section aria-labelledby="feed-title" className="flex flex-col gap-4 border-t border-line pt-6">
      <h2 id="feed-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {loadFailed && (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-danger-ink">{t("loadError")}</p>
          <Button variant="secondary" onClick={() => void load()}>
            {tAccount("retry")}
          </Button>
        </div>
      )}
      {preferences && (
        <>
          <div className="flex flex-col gap-1">
            <Switch
              label={t("personalised")}
              checked={preferences.personalised_feed}
              onCheckedChange={(checked) => {
                change({ personalised_feed: checked }, false);
              }}
            />
            <p className="text-sm text-ink-2">{t("personalisedHint")}</p>
          </div>
          <div className="trv-field">
            <div className="flex items-baseline justify-between">
              <label className="trv-field-label" htmlFor="feed-discovery">
                {t("discovery")}
              </label>
              <span aria-hidden="true" className="text-sm font-semibold tabular-nums">
                {t("discoveryValue", { value: preferences.feed_discovery_level })}
              </span>
            </div>
            <input
              id="feed-discovery"
              type="range"
              min={0}
              max={100}
              step={10}
              value={preferences.feed_discovery_level}
              aria-describedby="feed-discovery-hint"
              aria-valuetext={t("discoveryValue", { value: preferences.feed_discovery_level })}
              className="trv-range"
              onChange={(event) => {
                // Saved once the thumb stops moving.
                change({ feed_discovery_level: Number(event.target.value) }, true);
              }}
            />
            <div aria-hidden="true" className="flex justify-between text-xs text-ink-2">
              <span>{t("discoveryLow")}</span>
              <span>{t("discoveryHigh")}</span>
            </div>
            <p className="trv-field-hint" id="feed-discovery-hint">
              {t("discoveryHint")}
            </p>
          </div>
        </>
      )}
      {failed && (
        <p role="alert" className="text-sm text-danger-ink">
          {t("error")}
        </p>
      )}
    </section>
  );
}
