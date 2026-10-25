"use client";

import { Button, Dialog } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiFetch } from "@/lib/api";

type Viewer = { following: boolean; blocking: boolean };
type Action = "followed" | "unfollowed" | "blocked" | "unblocked";

type Props = {
  locale: string;
  userId: string;
  username: string;
  displayName: string;
  viewer: Viewer | null;
};

const REQUESTS: Record<Action, { path: "follow" | "block"; method: "POST" | "DELETE" }> = {
  followed: { path: "follow", method: "POST" },
  unfollowed: { path: "follow", method: "DELETE" },
  blocked: { path: "block", method: "POST" },
  unblocked: { path: "block", method: "DELETE" },
};

/** Follow and block (P1-T10) from the public profile; the page re-renders with the new counts. */
export function ProfileActions({ locale, userId, username, displayName, viewer }: Props) {
  const t = useTranslations("PublicProfile");
  const router = useRouter();
  const { me } = useSession();
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState<Action | null>(null);
  const primary = useRef<HTMLButtonElement>(null);

  // The buttons change once the page re-renders: focus goes to the one now in place.
  useEffect(() => {
    if (done && !pending) primary.current?.focus();
  }, [done, pending, viewer?.blocking, viewer?.following]);

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
  // The page was rendered for a visitor; the session says otherwise until the next load.
  if (me && !viewer) return null;
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

  function act(action: Action) {
    setFailed(false);
    setDone(null);
    const { path, method } = REQUESTS[action];
    startTransition(async () => {
      try {
        const response = await apiFetch(`/v1/users/${userId}/${path}`, { method });
        await response.body?.cancel();
        if (!response.ok) {
          setFailed(true);
          return;
        }
      } catch {
        setFailed(true); // Offline: a message, never the error page.
        return;
      }
      setConfirming(false);
      // Part of the transition: the buttons stay disabled until the new counts are shown.
      startTransition(() => {
        setDone(action);
        router.refresh();
      });
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {viewer.blocking ? (
          <Button
            ref={primary}
            variant="secondary"
            disabled={pending}
            onClick={() => {
              act("unblocked");
            }}
          >
            {t("unblock")}
          </Button>
        ) : (
          <>
            {viewer.following ? (
              <Button
                ref={primary}
                variant="secondary"
                disabled={pending}
                aria-label={t("unfollowLabel")}
                onClick={() => {
                  act("unfollowed");
                }}
              >
                {t("following")}
              </Button>
            ) : (
              <Button
                ref={primary}
                disabled={pending}
                onClick={() => {
                  act("followed");
                }}
              >
                {t("follow")}
              </Button>
            )}
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
                    act("blocked");
                  }}
                >
                  {t("blockConfirm")}
                </Button>
              </div>
            </Dialog>
          </>
        )}
      </div>
      {/* Always mounted: the result of each action is announced. */}
      <p role="status" className="text-sm text-ink-2">
        {done && !pending ? t(`done.${done}`, { name: displayName }) : ""}
      </p>
      {failed && (
        <p role="alert" className="text-sm text-danger-ink">
          {t("error")}
        </p>
      )}
    </div>
  );
}
