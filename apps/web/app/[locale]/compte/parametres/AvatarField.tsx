"use client";

import { Button } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useEffect, useId, useRef, useState } from "react";

import { MemberAvatar } from "@/components/Avatar";
import { useSession } from "@/components/SessionProvider";
import { apiCall } from "@/lib/api";
import { ACCEPTED_TYPES, type Media, uploadPhoto, type Variant } from "@/lib/media";

export type AvatarProfile = {
  display_name: string;
  avatar: Variant[] | null;
  version: number;
  flags: Record<string, boolean>;
};

/**
 * The profile photo (W20, P2-T02c): chosen, sent and processed, shown for confirmation, then
 * saved on the profile. Choosing is offered only while photo uploads are open (flag
 * `media.uploads`); removing always is.
 */
export function AvatarField<P extends AvatarProfile>({
  profile,
  onStored,
  onConflict,
  onSaved,
}: {
  profile: P | null;
  /** The profile as the API stored it: its new version and photo. */
  onStored: (stored: P) => void;
  /** Changed elsewhere meanwhile: the form takes the fresh profile and says so. */
  onConflict: (fresh: P) => void;
  onSaved: (message: string) => void;
}) {
  const t = useTranslations("Account.profile.avatar");
  const { refresh } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const chooseButton = useRef<HTMLButtonElement>(null);
  const saveButton = useRef<HTMLButtonElement>(null);
  const hintId = useId();
  const [pending, setPending] = useState<Media | null>(null);
  const [busy, setBusy] = useState<"sending" | "saving" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // Focus follows the buttons that replace the one just used (WCAG 2.4.3).
  const [focus, setFocus] = useState<"save" | "choose" | null>(null);
  const upload = useRef<AbortController | null>(null);

  useEffect(() => () => upload.current?.abort(), []);
  useEffect(() => {
    if (focus === "save") saveButton.current?.focus();
    if (focus === "choose") chooseButton.current?.focus();
  }, [focus, pending]);

  const canUpload = Boolean(profile?.flags["media.uploads"]);
  const shown = pending ? pending.variants : (profile?.avatar ?? null);

  async function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // the same file can be chosen again after a failure
    if (!file) return;
    setProblem(null);
    onSaved("");
    setBusy("sending");
    upload.current = new AbortController();
    const result = await uploadPhoto(file, "avatar", undefined, upload.current.signal);
    if (!result.ok && result.reason === "aborted") return; // the page was left
    setBusy(null);
    if (result.ok) {
      setPending(result.media);
      setFocus("save");
    } else {
      setProblem(t(`errors.${result.reason}`));
    }
  }

  async function save(mediaId: string | null) {
    if (!profile) return;
    setProblem(null);
    setBusy("saving");
    const result = await apiCall<P>("/v1/me", {
      method: "PATCH",
      headers: { "if-match": String(profile.version) },
      body: JSON.stringify({ avatar_media_id: mediaId }),
    });
    setBusy(null);
    if (result.ok) {
      setPending(null);
      setFocus("choose");
      onStored(result.data);
      onSaved(t(mediaId ? "saved" : "removed"));
      await refresh(); // the header shows the new photo
      return;
    }
    if (result.status === 412) {
      const fresh = await apiCall<P>("/v1/me");
      if (fresh.ok) onConflict(fresh.data);
      else setProblem(t("errors.error"));
      return;
    }
    setProblem(t("errors.error"));
  }

  return (
    <fieldset className="flex flex-col gap-3" aria-describedby={hintId}>
      <legend className="trv-field-label">{t("label")}</legend>
      <div className="flex items-center gap-4">
        <MemberAvatar name={profile?.display_name ?? ""} avatar={shown} size={96} />
        <div className="flex flex-col items-start gap-2">
          {pending ? (
            <div className="flex flex-wrap gap-2">
              <Button
                ref={saveButton}
                disabled={busy !== null}
                onClick={() => void save(pending.id)}
              >
                {busy === "saving" ? t("saving") : t("save")}
              </Button>
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() => {
                  setPending(null);
                  setProblem(null);
                  setFocus("choose");
                }}
              >
                {t("cancel")}
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {canUpload && (
                <>
                  <input
                    ref={input}
                    type="file"
                    accept={ACCEPTED_TYPES.join(",")}
                    className="sr-only"
                    tabIndex={-1}
                    aria-hidden="true"
                    onChange={(event) => void choose(event)}
                  />
                  <Button
                    ref={chooseButton}
                    variant="secondary"
                    disabled={!profile || busy !== null}
                    onClick={() => input.current?.click()}
                  >
                    {busy === "sending" ? t("sending") : t(profile?.avatar ? "change" : "choose")}
                  </Button>
                </>
              )}
              {profile?.avatar && (
                <Button
                  variant="secondary"
                  disabled={busy !== null}
                  onClick={() => void save(null)}
                >
                  {t("remove")}
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
      <p className="trv-field-hint" id={hintId}>
        {canUpload ? t("hint") : t("unavailable")}
      </p>
      {/* Announced: the photo being prepared, then the preview to confirm. */}
      <div aria-live="polite" className="text-sm">
        {busy === "sending" && <p>{t("processing")}</p>}
        {pending && <p>{t("preview")}</p>}
      </div>
      {problem && (
        <p role="alert" className="text-sm text-danger-ink">
          {problem}
        </p>
      )}
    </fieldset>
  );
}
