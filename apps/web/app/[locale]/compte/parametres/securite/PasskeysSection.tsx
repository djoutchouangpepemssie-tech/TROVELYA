"use client";

import { Button, Dialog, Input } from "@trovelya/ui";
import { useFormatter, useTranslations } from "next-intl";
import { type SyntheticEvent, useCallback, useEffect, useRef, useState } from "react";

import { apiCall, type ApiResult } from "@/lib/api";
import { registerPasskey } from "@/lib/passkeys";

type StepUp = <T>(
  action: () => Promise<ApiResult<T>>,
  options?: { retry?: boolean },
) => Promise<ApiResult<T>>;
type Passkey = { id: string; name: string | null; created_at: string; last_used_at: string | null };

const NAME_MAX = 64;

/** Passkeys (T04): add (step-up), rename, delete (step-up). Shown while the feature is on. */
export function PasskeysSection({
  stepUp,
  onDone,
}: {
  stepUp: StepUp;
  onDone: (message: string) => void;
}) {
  const t = useTranslations("Account.security.passkeys");
  const tAccount = useTranslations("Account");
  const format = useFormatter();
  const [passkeys, setPasskeys] = useState<Passkey[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState<Passkey | null>(null);
  const [nameMissing, setNameMissing] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);

  // After a change that removes the focused control, focus goes to a stable place: the
  // row's first button (rename), or the section title once the row is gone.
  function focusRow(id: string) {
    requestAnimationFrame(() => {
      list.current?.querySelector<HTMLButtonElement>(`[data-passkey="${id}"] button`)?.focus();
    });
  }

  const load = useCallback(async () => {
    setLoadFailed(false);
    const result = await apiCall<{ data: Passkey[] }>("/v1/me/passkeys");
    if (result.ok) setPasskeys(result.data.data);
    else setLoadFailed(true);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const label = (passkey: Passkey) => passkey.name ?? t("defaultName");

  async function act(action: () => Promise<ApiResult<unknown>>, message: string): Promise<boolean> {
    setBusy(true);
    setFailed(null);
    onDone("");
    const result = await action();
    setBusy(false);
    if (result.ok) {
      onDone(message);
      await load();
      return true;
    }
    // The step-up dialog explains itself; a browser prompt closed by the person is no error.
    if (result.code === "step_up_confirmed") setFailed(t("confirmedClickAgain"));
    else if (!["step_up_pending", "step_up_cancelled", "cancelled"].includes(result.code)) {
      setFailed(result.code === "unsupported" ? t("unsupported") : t("error"));
    }
    return false;
  }

  async function add(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    // No name: none is stored, the list shows a translated default.
    const name = newName.trim();
    const added = await act(
      () =>
        stepUp(
          async () => {
            const result = await registerPasskey(name);
            return result.ok
              ? { ok: true as const, data: result.value }
              : {
                  ok: false as const,
                  status: result.error === "step_up_required" ? 403 : 0,
                  code: result.error,
                };
          },
          // The browser prompt needs a fresh click after the confirmation.
          { retry: false },
        ),
      t("added"),
    );
    if (added) setNewName("");
  }

  async function rename(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renaming) return;
    const name = renaming.name.trim();
    if (!name) {
      setNameMissing(true);
      return;
    }
    setNameMissing(false);
    const id = renaming.id;
    const renamed = await act(
      () =>
        apiCall(`/v1/me/passkeys/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ name }),
        }),
      t("renamed"),
    );
    if (renamed) {
      setRenaming(null);
      focusRow(id);
    }
  }

  async function remove() {
    if (!deleting) return;
    const id = deleting.id;
    setDeleting(null);
    const removed = await act(
      () => stepUp(() => apiCall(`/v1/me/passkeys/${id}`, { method: "DELETE" })),
      t("deleted"),
    );
    // Its row is gone: focus goes to the section title.
    if (removed) heading.current?.focus();
  }

  return (
    <section
      aria-labelledby="passkeys-title"
      className="flex flex-col gap-3 border-t border-line pt-6"
    >
      <h2 id="passkeys-title" ref={heading} tabIndex={-1} className="text-xl font-semibold">
        {t("title")}
      </h2>
      <p className="text-sm text-ink-2">{t("intro")}</p>
      {loadFailed && (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-danger-ink">{t("loadError")}</p>
          <Button variant="secondary" onClick={() => void load()}>
            {tAccount("retry")}
          </Button>
        </div>
      )}
      {passkeys?.length === 0 && <p className="text-ink-2">{t("none")}</p>}
      {passkeys && passkeys.length > 0 && (
        <ul ref={list} className="divide-y divide-line rounded-xl border border-line">
          {passkeys.map((passkey) => (
            <li
              key={passkey.id}
              data-passkey={passkey.id}
              className="flex flex-col gap-2 px-4 py-3"
            >
              {renaming?.id === passkey.id ? (
                <form onSubmit={(event) => void rename(event)} className="flex flex-col gap-2">
                  <Input
                    label={t("name")}
                    value={renaming.name}
                    maxLength={NAME_MAX}
                    autoFocus
                    onChange={(event) => {
                      setRenaming({ id: passkey.id, name: event.target.value });
                    }}
                    {...(nameMissing ? { error: t("nameRequired") } : {})}
                  />
                  <div className="flex gap-2">
                    <Button type="submit" size="sm" disabled={busy}>
                      {t("save")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setRenaming(null);
                        setNameMissing(false);
                        focusRow(passkey.id);
                      }}
                    >
                      {t("cancel")}
                    </Button>
                  </div>
                </form>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{label(passkey)}</p>
                    <p className="text-sm text-ink-2">
                      {t("created", {
                        date: format.dateTime(new Date(passkey.created_at), {
                          dateStyle: "medium",
                        }),
                      })}
                      {" · "}
                      {passkey.last_used_at
                        ? t("lastUsed", {
                            date: format.dateTime(new Date(passkey.last_used_at), {
                              dateStyle: "medium",
                            }),
                          })
                        : t("neverUsed")}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("renameLabel", { name: label(passkey) })}
                      onClick={() => {
                        setRenaming({ id: passkey.id, name: passkey.name ?? "" });
                      }}
                    >
                      {t("rename")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("deleteLabel", { name: label(passkey) })}
                      onClick={() => {
                        setDeleting(passkey);
                      }}
                    >
                      {t("delete")}
                    </Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t("deleteTitle", { name: deleting ? label(deleting) : "" })}
        description={t("deleteDescription")}
        closeLabel={t("close")}
      >
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setDeleting(null);
            }}
          >
            {t("cancel")}
          </Button>
          <Button variant="danger" onClick={() => void remove()}>
            {t("deleteConfirm")}
          </Button>
        </div>
      </Dialog>
      <form onSubmit={(event) => void add(event)} className="flex flex-col gap-3">
        <Input
          label={t("addName")}
          hint={t("addHint")}
          value={newName}
          maxLength={NAME_MAX}
          onChange={(event) => {
            setNewName(event.target.value);
          }}
        />
        <Button type="submit" variant="secondary" disabled={busy} className="self-start">
          {t("add")}
        </Button>
      </form>
      {failed && (
        <p role="alert" className="text-sm text-danger-ink">
          {failed}
        </p>
      )}
    </section>
  );
}
