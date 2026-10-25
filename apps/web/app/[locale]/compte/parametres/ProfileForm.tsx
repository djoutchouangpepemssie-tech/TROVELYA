"use client";

import { Button, Input } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiCall } from "@/lib/api";

type Profile = {
  username: string;
  display_name: string;
  bio: string | null;
  locale: string;
  version: number;
};
type Field = "username" | "displayName";
type Problem = { field: Field | null; key: string };

// Same rule as the API (USERNAME_PATTERN).
const USERNAME = /^[a-z0-9_.]{3,30}$/;
const BIO_MAX = 500;

/** Pseudo, name, bio and language; saved with `If-Match` on the version that was read. */
export function ProfileForm({ onSaved }: { onSaved: (message: string) => void }) {
  const t = useTranslations("Account.profile");
  const tAccount = useTranslations("Account");
  const { refresh } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [problem, setProblem] = useState<Problem | null>(null);
  const [saving, setSaving] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);
  const displayNameRef = useRef<HTMLInputElement>(null);

  const [loadFailed, setLoadFailed] = useState(false);

  function show(stored: Profile) {
    setProfile(stored);
    setUsername(stored.username);
    setDisplayName(stored.display_name);
    setBio(stored.bio ?? "");
  }

  async function load(): Promise<void> {
    setLoadFailed(false);
    const result = await apiCall<Profile>("/v1/me");
    if (result.ok) show(result.data);
    else setLoadFailed(true);
  }

  useEffect(() => {
    void load();
  }, []);

  function fail(next: Problem) {
    setProblem(next);
    if (next.field === "username") usernameRef.current?.focus();
    if (next.field === "displayName") displayNameRef.current?.focus();
  }

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile) return;
    const name = displayName.trim();
    if (!USERNAME.test(username)) {
      fail({ field: "username", key: "usernameFormat" });
      return;
    }
    if (!name) {
      fail({ field: "displayName", key: "displayNameRequired" });
      return;
    }
    setProblem(null);
    onSaved("");
    setSaving(true);
    const result = await apiCall<Profile>("/v1/me", {
      method: "PATCH",
      headers: { "if-match": String(profile.version) },
      body: JSON.stringify({ username, display_name: name, bio: bio.trim() || null }),
    });
    setSaving(false);
    if (result.ok) {
      show(result.data); // What the API stored (the bio trimmed, for instance).
      onSaved(t("saved"));
      // The header and the account hub show the new name.
      await refresh();
      return;
    }
    if (result.code === "username_taken") {
      fail({ field: "username", key: "usernameTaken" });
      return;
    }
    if (result.status === 412) {
      // Changed elsewhere (another tab or device): keep what the member typed, take the new
      // version, and let them save again knowingly.
      const fresh = await apiCall<Profile>("/v1/me");
      if (fresh.ok) setProfile(fresh.data);
      fail({ field: null, key: "stale" });
      return;
    }
    fail({ field: null, key: "error" });
  }

  const error = (field: Field) =>
    problem?.field === field ? { error: t(`errors.${problem.key}`) } : {};

  if (loadFailed) {
    return (
      <div role="alert" className="flex flex-col items-start gap-2">
        <p className="text-danger-ink">{t("loadError")}</p>
        <Button variant="secondary" onClick={() => void load()}>
          {tAccount("retry")}
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-4">
      <Input
        ref={usernameRef}
        label={t("username")}
        hint={t("usernameHint")}
        value={username}
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        maxLength={30}
        disabled={!profile}
        onChange={(event) => {
          setUsername(event.target.value.toLowerCase());
        }}
        {...error("username")}
      />
      <Input
        ref={displayNameRef}
        label={t("displayName")}
        hint={t("displayNameHint")}
        value={displayName}
        autoComplete="name"
        maxLength={60}
        disabled={!profile}
        onChange={(event) => {
          setDisplayName(event.target.value);
        }}
        {...error("displayName")}
      />
      <div className="trv-field">
        <label className="trv-field-label" htmlFor="profile-bio">
          {t("bio")}
        </label>
        <textarea
          id="profile-bio"
          className="trv-input min-h-28 py-3"
          value={bio}
          maxLength={BIO_MAX}
          disabled={!profile}
          aria-describedby="profile-bio-hint"
          onChange={(event) => {
            setBio(event.target.value);
          }}
        />
        <p className="trv-field-hint" id="profile-bio-hint">
          {t("bioHint")} {bio.length}/{BIO_MAX}
        </p>
      </div>
      <div className="trv-field">
        <label className="trv-field-label" htmlFor="profile-language">
          {t("language")}
        </label>
        {/* French only until P18 (the other EU languages). */}
        <select id="profile-language" className="trv-input" value="fr-FR" disabled>
          <option value="fr-FR">{t("languageFr")}</option>
        </select>
      </div>
      {problem && problem.field === null && (
        <p role="alert" className="text-sm text-danger-ink">
          {t(`errors.${problem.key}`)}
        </p>
      )}
      <Button type="submit" disabled={!profile || saving} className="self-start">
        {saving ? t("saving") : t("save")}
      </Button>
    </form>
  );
}
