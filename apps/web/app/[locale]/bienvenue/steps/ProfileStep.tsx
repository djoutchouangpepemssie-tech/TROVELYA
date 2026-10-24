"use client";

import { Button, Checkbox, Input } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import { TERMS_VERSION } from "@/lib/legal";

import { onboardingApi } from "../api";
import { StepLayout } from "../StepLayout";

const USERNAME = /^[a-z0-9_.]{3,30}$/;

type Errors = { username?: string; displayName?: string; birthYear?: string; terms?: string };

export function ProfileStep({ onCompleted }: { onCompleted: () => void }) {
  const t = useTranslations("Onboarding");
  const locale = useLocale();
  const [username, setUsername] = useState("");
  const usernameTouched = useRef(false); // a late suggestion never overwrites what was typed
  const [displayName, setDisplayName] = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [terms, setTerms] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [tooYoung, setTooYoung] = useState(false);
  const [sending, setSending] = useState(false);
  const usernameInput = useRef<HTMLInputElement>(null);
  const displayNameInput = useRef<HTMLInputElement>(null);
  const birthYearInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void (async () => {
      const suggestion = await onboardingApi.usernameSuggestion();
      if (suggestion.ok && !usernameTouched.current) setUsername(suggestion.data.username);
    })();
  }, []);

  function validate(): Errors {
    const found: Errors = {};
    const year = Number(birthYear);
    if (!USERNAME.test(username.trim().toLowerCase()))
      found.username = t("profile.usernameInvalid");
    if (!displayName.trim()) found.displayName = t("profile.displayNameRequired");
    if (!/^\d{4}$/.test(birthYear) || year < 1900 || year > new Date().getFullYear()) {
      found.birthYear = t("profile.birthYearInvalid");
    }
    if (!terms) found.terms = t("profile.termsRequired");
    return found;
  }

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) {
      if (found.username) usernameInput.current?.focus();
      else if (found.displayName) displayNameInput.current?.focus();
      else if (found.birthYear) birthYearInput.current?.focus();
      return;
    }
    setSending(true);
    const result = await onboardingApi.completeProfile({
      username: username.trim().toLowerCase(),
      display_name: displayName.trim(),
      birth_year: Number(birthYear),
      accept_terms: true,
      terms_version: TERMS_VERSION,
    });
    setSending(false);
    if (result.ok) {
      onCompleted();
    } else if (result.code === "too_young") {
      setTooYoung(true);
    } else if (result.code === "username_taken") {
      setErrors({ username: t("profile.usernameTaken") });
      usernameInput.current?.focus();
    } else if (result.code === "profile_already_completed") {
      onCompleted();
    } else {
      setFailure(t("error"));
    }
  }

  if (tooYoung) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-4 px-5">
        <h1 className="text-3xl leading-tight font-bold tracking-tight">
          {t("profile.tooYoungTitle")}
        </h1>
        <p className="text-ink-2">{t("profile.tooYoungBody")}</p>
        <a href={`/${locale}`} className="trv-button self-start" data-variant="secondary">
          {t("profile.backHome")}
        </a>
      </main>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <StepLayout
        step={1}
        title={t("profile.title")}
        intro={t("profile.intro")}
        error={failure}
        actions={
          <Button type="submit" size="lg" disabled={sending}>
            {t("profile.submit")}
          </Button>
        }
      >
        <div className="flex flex-col gap-5">
          <Input
            ref={usernameInput}
            label={t("profile.username")}
            hint={t("profile.usernameHint")}
            {...(errors.username ? { error: errors.username } : {})}
            value={username}
            onChange={(event) => {
              usernameTouched.current = true;
              setUsername(event.target.value);
            }}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={30}
          />
          <Input
            ref={displayNameInput}
            label={t("profile.displayName")}
            hint={t("profile.displayNameHint")}
            {...(errors.displayName ? { error: errors.displayName } : {})}
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
            }}
            autoComplete="nickname"
            maxLength={60}
          />
          <Input
            ref={birthYearInput}
            label={t("profile.birthYear")}
            hint={t("profile.birthYearHint")}
            {...(errors.birthYear ? { error: errors.birthYear } : {})}
            value={birthYear}
            onChange={(event) => {
              setBirthYear(event.target.value.replace(/\D/g, "").slice(0, 4));
            }}
            inputMode="numeric"
            autoComplete="bday-year"
            maxLength={4}
          />
          <div>
            <Checkbox label={t("profile.terms")} checked={terms} onCheckedChange={setTerms} />
            <a
              className="mt-1 inline-block text-sm text-brand underline underline-offset-2"
              href={`/${locale}/legal/cgu`}
              target="_blank"
              rel="noopener"
            >
              {t("profile.termsLink")}
            </a>
            {errors.terms ? (
              <p role="alert" className="trv-field-error mt-1">
                {errors.terms}
              </p>
            ) : null}
          </div>
        </div>
      </StepLayout>
    </form>
  );
}
