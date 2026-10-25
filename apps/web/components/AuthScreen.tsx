"use client";

import { Button, Input, Logo } from "@trovelya/ui";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import {
  type AuthMethods,
  authApi,
  rememberNext,
  type RequestResult,
  safeNext,
  takeNext,
} from "@/lib/auth";
import { type PasskeyError, signInWithPasskey } from "@/lib/passkeys";

import { useSession } from "./SessionProvider";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type Mode = "signIn" | "signUp";

/** W06: sign-in and sign-up are the same journey (the « Welcome » mock-up). */
export function AuthScreen({ mode }: { mode: Mode }) {
  const t = useTranslations("Auth");
  const locale = useLocale();
  const router = useRouter();
  const search = useSearchParams();
  const { me, refresh } = useSession();
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [email, setEmail] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<RequestResult | null>(null);
  const [passkeyError, setPasskeyError] = useState<PasskeyError | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const sentRef = useRef<HTMLParagraphElement>(null);
  const oauthError = search.get("erreur");
  const next = safeNext(search.get("suivant"));

  useEffect(() => {
    rememberNext(search.get("suivant"));
  }, [search]);

  useEffect(() => {
    void authApi.methods().then(setMethods);
  }, []);

  // The form (and its focused button) is replaced by the confirmation: focus goes there.
  useEffect(() => {
    if (result === "sent") sentRef.current?.focus();
  }, [result]);

  // Already signed in: straight to where the person was going.
  useEffect(() => {
    if (me)
      router.replace(me.profile_completed ? (takeNext() ?? `/${locale}`) : `/${locale}/bienvenue`);
  }, [me, router, locale]);

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim();
    if (!EMAIL.test(address)) {
      setInvalid(true);
      emailRef.current?.focus();
      return;
    }
    setInvalid(false);
    setSending(true);
    setResult(await authApi.requestMagicLink(address));
    setSending(false);
  }

  async function passkey() {
    setPasskeyError(null);
    const signed = await signInWithPasskey();
    if (!signed.ok) {
      setPasskeyError(signed.error);
      return;
    }
    // The header and tabs live in the layout: they learn of the new session here, and the
    // "already signed in" effect above then takes the person on.
    await refresh();
  }

  const title = mode === "signIn" ? t("signInTitle") : t("signUpTitle");
  const submitLabel = mode === "signIn" ? t("emailSubmitSignIn") : t("emailSubmitSignUp");
  const providers = methods
    ? (["apple", "google"] as const).filter((provider) => methods[provider])
    : [];

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-3.5rem)] w-full max-w-md flex-col justify-center gap-6 px-4 py-10">
      <div className="flex flex-col items-center gap-3 text-center">
        <Logo label={t("logo")} size={56} />
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="text-ink-2">{t("intro")}</p>
      </div>

      {oauthError && (
        <p role="alert" className="text-danger-ink">
          {t("oauthFailed")}
        </p>
      )}

      {(providers.length > 0 || methods?.passkey) && (
        <div className="flex flex-col gap-3">
          {providers.map((provider) => (
            <a
              key={provider}
              href={`/api/v1/auth/oauth/${provider}/start`}
              className="trv-button"
              data-variant="secondary"
              data-size="lg"
            >
              {t(provider)}
            </a>
          ))}
          {methods?.passkey && (
            <Button variant="secondary" size="lg" onClick={() => void passkey()}>
              {t("passkey")}
            </Button>
          )}
          {passkeyError && (
            <p role="alert" className="text-sm text-danger-ink">
              {t(`passkeyErrors.${passkeyError}`)}
            </p>
          )}
          <p className="text-center text-sm text-ink-2">{t("or")}</p>
        </div>
      )}

      {/* Mounted from the start (empty), so screen readers announce what appears in it. */}
      <div role="status" className="empty:-mt-6">
        {result === "sent" && (
          <div className="flex flex-col gap-3 rounded-lg bg-surface-2 p-4">
            <p ref={sentRef} tabIndex={-1} className="font-medium">
              {t("sent")}
            </p>
            <p className="text-sm text-ink-2">
              {methods
                ? t("sentHint", { minutes: methods.magic_link_ttl_min })
                : t("sentHintShort")}
            </p>
            <Button
              variant="ghost"
              onClick={() => {
                setResult(null);
                setEmail("");
                requestAnimationFrame(() => emailRef.current?.focus());
              }}
            >
              {t("otherEmail")}
            </Button>
          </div>
        )}
      </div>
      {result !== "sent" && (
        <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-3">
          <Input
            ref={emailRef}
            label={t("emailLabel")}
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
            {...(invalid ? { error: t("emailInvalid") } : {})}
          />
          {result && (
            <p role="alert" className="text-sm text-danger-ink">
              {t(`requestErrors.${result}`)}
            </p>
          )}
          <Button type="submit" size="lg" disabled={sending}>
            {submitLabel}
          </Button>
        </form>
      )}

      <p className="text-center text-sm">
        <a
          className="font-medium text-ink underline underline-offset-2"
          href={`/${locale}/${mode === "signIn" ? "inscription" : "connexion"}${next ? `?suivant=${encodeURIComponent(next)}` : ""}`}
        >
          {mode === "signIn" ? t("switchToSignUp") : t("switchToSignIn")}
        </a>
      </p>
    </main>
  );
}
