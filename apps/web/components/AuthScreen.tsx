"use client";

import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { type CSSProperties, type SyntheticEvent, useEffect, useRef, useState } from "react";

import "./welcome.css";

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
    <main className="trv-welcome relative min-h-dvh overflow-hidden bg-[#07070C] text-white antialiased">
      <div className="relative mx-auto flex min-h-dvh w-full max-w-[390px] flex-col px-5 pb-10">
        {/* The « Welcome » mock-up: three photos in glass frames over two blurred lights. */}
        <div aria-hidden="true" className="relative -mx-5 h-[456px] shrink-0">
          <div className="absolute top-[120px] left-[40px] h-[320px] w-[320px] rounded-full bg-[#1D2BFF] opacity-75 blur-[90px]" />
          <div className="absolute top-[300px] left-[210px] h-[200px] w-[200px] rounded-full bg-[#E05C38] opacity-35 blur-[90px]" />
          {WELCOME_TILES.map((tile) => (
            <div
              key={tile.src}
              className="trv-glass absolute overflow-hidden rounded-[28px] p-1.5"
              style={tile.style}
            >
              <Image
                src={tile.src}
                alt=""
                width={360}
                height={450}
                priority
                className="h-full w-full rounded-[22px] object-cover"
              />
            </div>
          ))}
          <div className="trv-glass absolute top-[380px] left-[230px] flex items-center gap-1.5 rounded-full px-3 py-2 text-[13px] font-semibold">
            <span className="h-[7px] w-[7px] rounded-full bg-[#E0352B]" />
            {t("welcomeLive")}
          </div>
          <div className="trv-glass absolute top-[306px] left-[16px] rounded-full px-3 py-2 font-mono text-[13px] font-semibold">
            {t("welcomeAuction")}
          </div>
        </div>

        <div className="mt-[22px]">
          <p className="text-[52px] leading-none font-bold tracking-[-0.05em]">{t("logo")}</p>
          <h1 className="sr-only">{title}</h1>
          <p className="mt-2.5 text-[22px] leading-tight font-medium tracking-[-0.02em] text-white/85">
            {t("welcomeTagline")}
            <br />
            <span className="text-base font-normal text-white/70">{t("welcomeSubline")}</span>
          </p>
        </div>

        <div className="mt-auto flex flex-col gap-2.5 pt-8">
          {oauthError && (
            <p role="alert" className="text-sm text-[#FF8A8F]">
              {t("oauthFailed")}
            </p>
          )}
          {/* A full page load: the API starts the OAuth redirect (not a page of this app). */}
          {providers.map((provider) => (
            <a
              key={provider}
              href={`/api/v1/auth/oauth/${provider}/start`}
              className={`trv-welcome-button ${provider === "apple" ? "bg-white text-[#0B0B0F]" : "trv-glass relative text-white"}`}
            >
              {provider === "apple" && <AppleLogo />}
              {t(provider)}
            </a>
          ))}
          {methods?.passkey && (
            <button
              type="button"
              className="trv-welcome-button trv-glass relative text-white"
              onClick={() => void passkey()}
            >
              {t("passkey")}
            </button>
          )}
          {passkeyError && (
            <p role="alert" className="text-sm text-[#FF8A8F]">
              {t(`passkeyErrors.${passkeyError}`)}
            </p>
          )}

          {/* Mounted from the start (empty), so screen readers announce what appears in it. */}
          <div role="status" className="empty:-mt-2.5">
            {result === "sent" && (
              <div className="trv-glass relative flex flex-col gap-2 rounded-3xl p-4">
                <p ref={sentRef} tabIndex={-1} className="font-semibold">
                  {t("sent")}
                </p>
                <p className="text-sm text-white/75">
                  {methods
                    ? t("sentHint", { minutes: methods.magic_link_ttl_min })
                    : t("sentHintShort")}
                </p>
                <button
                  type="button"
                  className="self-start text-sm font-semibold text-white underline underline-offset-2"
                  onClick={() => {
                    setResult(null);
                    setEmail("");
                    requestAnimationFrame(() => emailRef.current?.focus());
                  }}
                >
                  {t("otherEmail")}
                </button>
              </div>
            )}
          </div>
          {result !== "sent" && (
            <form
              onSubmit={(event) => void submit(event)}
              noValidate
              className="flex flex-col gap-2.5"
            >
              <label htmlFor="auth-email" className="text-sm font-medium text-white/80">
                {t("emailLabel")}
              </label>
              <input
                ref={emailRef}
                id="auth-email"
                type="email"
                autoComplete="email"
                inputMode="email"
                value={email}
                aria-invalid={invalid}
                aria-describedby={invalid ? "auth-email-error" : undefined}
                onChange={(event) => {
                  setEmail(event.target.value);
                }}
                className="trv-glass relative h-[54px] rounded-full px-5 text-[17px] text-white placeholder:text-white/50 aria-[invalid=true]:outline aria-[invalid=true]:outline-2 aria-[invalid=true]:outline-[#FF8A8F]"
              />
              {invalid && (
                <p id="auth-email-error" role="alert" className="text-sm text-[#FF8A8F]">
                  {t("emailInvalid")}
                </p>
              )}
              {result && (
                <p role="alert" className="text-sm text-[#FF8A8F]">
                  {t(`requestErrors.${result}`)}
                </p>
              )}
              <button
                type="submit"
                disabled={sending}
                className="trv-welcome-button bg-white text-[#0B0B0F] disabled:opacity-60"
              >
                {submitLabel}
              </button>
            </form>
          )}

          <a
            className="py-2.5 text-center text-[15px] font-medium text-white/80 hover:text-white"
            href={`/${locale}/${mode === "signIn" ? "inscription" : "connexion"}${next ? `?suivant=${encodeURIComponent(next)}` : ""}`}
          >
            {mode === "signIn" ? t("switchToSignUp") : t("switchToSignIn")}
          </a>
          <p className="text-center text-[11px] text-white/55">{t("welcomeFootnote")}</p>
        </div>
      </div>
    </main>
  );
}

// Positions and tilts of the mock-up's photo frames (390 px wide screen).
const WELCOME_TILES: { src: string; style: CSSProperties }[] = [
  {
    src: "/welcome/montre.jpg",
    style: { left: 26, top: 70, width: 168, height: 210, transform: "rotate(-6deg)" },
  },
  {
    src: "/welcome/fleurs-du-mal.jpg",
    style: { left: 196, top: 50, width: 168, height: 210, transform: "rotate(5deg)" },
  },
  {
    src: "/welcome/lampe-opaline.jpg",
    style: { left: 110, top: 224, width: 176, height: 220, transform: "rotate(-1deg)" },
  },
];

function AppleLogo() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M16.4 12.6c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9-.7 0-1.8-.8-3-.8-1.6 0-3 .9-3.8 2.3-1.6 2.8-.4 6.9 1.2 9.2.8 1.1 1.7 2.4 2.9 2.3 1.2 0 1.6-.7 3-.7s1.8.7 3 .7c1.3 0 2.1-1.1 2.8-2.3.9-1.3 1.3-2.6 1.3-2.6s-2.5-1-2.5-3.7zM14.1 5.8c.6-.8 1.1-1.8 1-2.8-.9 0-2 .6-2.7 1.4-.6.7-1.1 1.7-1 2.7 1 .1 2-.5 2.7-1.3z" />
    </svg>
  );
}
