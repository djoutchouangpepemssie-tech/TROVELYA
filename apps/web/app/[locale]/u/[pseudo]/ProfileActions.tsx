"use client";

import { Button, Dialog } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiFetch } from "@/lib/api";

type Props = {
  locale: string;
  userId: string;
  username: string;
  displayName: string;
  viewer: { following: boolean; blocking: boolean } | null;
};

/** Follow and block (P1-T10) from the public profile; the page re-renders with the new counts. */
export function ProfileActions({ locale, userId, username, displayName, viewer }: Props) {
  const t = useTranslations("PublicProfile");
  const router = useRouter();
  const { me } = useSession();
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);

  if (me === undefined) return null;
  if (me?.username === username) {
    return (
      <a
        href={`/${locale}/compte/parametres`}
        className="trv-button self-start"
        data-variant="secondary"
      >
        {t("edit")}
      </a>
    );
  }
  if (!me || !viewer) {
    return (
      <a
        href={`/${locale}/connexion?suivant=${encodeURIComponent(`/${locale}/u/${username}`)}`}
        className="trv-button self-start"
        data-variant="primary"
      >
        {t("signInToFollow")}
      </a>
    );
  }

  function act(path: "follow" | "block", method: "POST" | "DELETE") {
    setFailed(false);
    startTransition(async () => {
      const response = await apiFetch(`/v1/users/${userId}/${path}`, { method });
      await response.body?.cancel();
      if (!response.ok) {
        setFailed(true);
        return;
      }
      setConfirming(false);
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {!viewer.blocking &&
          (viewer.following ? (
            <Button
              variant="secondary"
              disabled={pending}
              title={t("unfollowHint")}
              onClick={() => {
                act("follow", "DELETE");
              }}
            >
              {t("following")}
            </Button>
          ) : (
            <Button
              disabled={pending}
              onClick={() => {
                act("follow", "POST");
              }}
            >
              {t("follow")}
            </Button>
          ))}
        {viewer.blocking ? (
          <Button
            variant="ghost"
            disabled={pending}
            onClick={() => {
              act("block", "DELETE");
            }}
          >
            {t("unblock")}
          </Button>
        ) : (
          <Dialog
            open={confirming}
            onOpenChange={setConfirming}
            title={t("blockTitle", { name: displayName })}
            description={t("blockDescription")}
            closeLabel={t("close")}
            trigger={<Button variant="ghost">{t("block")}</Button>}
          >
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setConfirming(false);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                variant="danger"
                disabled={pending}
                onClick={() => {
                  act("block", "POST");
                }}
              >
                {t("blockConfirm")}
              </Button>
            </div>
          </Dialog>
        )}
      </div>
      {failed && (
        <p role="alert" className="text-sm text-danger-ink">
          {t("error")}
        </p>
      )}
    </div>
  );
}
