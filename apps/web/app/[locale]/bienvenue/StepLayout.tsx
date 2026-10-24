"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useRef } from "react";

export const TOTAL_STEPS = 4;

type StepLayoutProps = {
  step: number;
  title: string;
  intro?: string;
  error?: string | null;
  children: ReactNode;
  actions: ReactNode;
};

/** One onboarding step (maquette Onboard): progress bar, title, content, sticky actions.
 * The title takes the focus when the step appears, so keyboard and screen reader users
 * land at the start of the new step. */
export function StepLayout({ step, title, intro, error, children, actions }: StepLayoutProps) {
  const t = useTranslations("Onboarding");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col px-5 pt-14 pb-8">
      <div
        role="progressbar"
        aria-label={t("progress", { step, total: TOTAL_STEPS })}
        aria-valuemin={1}
        aria-valuemax={TOTAL_STEPS}
        aria-valuenow={step}
        className="flex gap-1.5"
      >
        {Array.from({ length: TOTAL_STEPS }, (_, index) => (
          <span
            key={index}
            className={`h-1 flex-1 rounded-sm ${index < step ? "bg-brand" : "bg-line"}`}
          />
        ))}
      </div>
      <h1
        ref={heading}
        tabIndex={-1}
        className="mt-6 text-3xl leading-tight font-bold tracking-tight outline-none"
      >
        {title}
      </h1>
      {intro ? <p className="mt-1.5 text-ink-2">{intro}</p> : null}
      <p role="alert" className="mt-3 empty:hidden text-danger">
        {error ?? ""}
      </p>
      <div className="mt-6 flex-1">{children}</div>
      <div className="sticky bottom-0 mt-8 flex flex-col gap-2.5 bg-surface pt-3 pb-2">
        {actions}
      </div>
    </main>
  );
}
