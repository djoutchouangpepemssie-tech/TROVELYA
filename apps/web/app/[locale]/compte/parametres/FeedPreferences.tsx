"use client";

import { Switch } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { apiCall } from "@/lib/api";

import type { Preferences } from "../../bienvenue/api";

/** The feed preferences of W20: personalised feed and the share of discovery (0 to 100). */
export function FeedPreferences({ onSaved }: { onSaved: (message: string) => void }) {
  const t = useTranslations("Account.feed");
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [level, setLevel] = useState(50);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The latest stored preferences: two quick changes must not overwrite each other.
  const stored = useRef<Preferences | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await apiCall<Preferences>("/v1/me/preferences");
      if (!result.ok) {
        setFailed(true);
        return;
      }
      stored.current = result.data;
      setPreferences(result.data);
      setLevel(result.data.feed_discovery_level);
    })();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  // Preferences are replaced as a whole (PUT): send the stored ones with this change only.
  async function save(changes: Partial<Preferences>) {
    const previous = stored.current;
    if (!previous) return;
    const next = { ...previous, ...changes };
    stored.current = next;
    setPreferences(next);
    setFailed(false);
    onSaved("");
    const result = await apiCall<Preferences>("/v1/me/preferences", {
      method: "PUT",
      body: JSON.stringify(next),
    });
    if (!result.ok) {
      // Back to what is stored, so the screen does not show an unsaved choice.
      stored.current = previous;
      setPreferences(previous);
      setLevel(previous.feed_discovery_level);
      setFailed(true);
      return;
    }
    onSaved(t("saved"));
  }

  return (
    <section aria-labelledby="feed-title" className="flex flex-col gap-4 border-t border-line pt-6">
      <h2 id="feed-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {preferences && (
        <>
          <div className="flex flex-col gap-1">
            <Switch
              label={t("personalised")}
              checked={preferences.personalised_feed}
              onCheckedChange={(checked) => void save({ personalised_feed: checked })}
            />
            <p className="text-sm text-ink-2">{t("personalisedHint")}</p>
          </div>
          <div className="trv-field">
            <label className="trv-field-label" htmlFor="feed-discovery">
              {t("discovery")}
            </label>
            <input
              id="feed-discovery"
              type="range"
              min={0}
              max={100}
              step={10}
              value={level}
              aria-describedby="feed-discovery-hint"
              aria-valuetext={`${String(level)} %`}
              className="accent-[var(--trv-color-brand)]"
              onChange={(event) => {
                const value = Number(event.target.value);
                setLevel(value);
                // Saved once the thumb stops moving.
                if (timer.current) clearTimeout(timer.current);
                timer.current = setTimeout(() => void save({ feed_discovery_level: value }), 600);
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
