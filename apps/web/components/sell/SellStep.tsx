"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useRef } from "react";

export const SELL_STEPS = 4;

/** One step of W09: progress, title (focused when the step appears), content, sticky actions. */
export function SellStep({
  step,
  title,
  intro,
  children,
  actions,
}: {
  step: number;
  title: string;
  intro?: string;
  children: ReactNode;
  actions: ReactNode;
}) {
  const t = useTranslations("Sell");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col px-5 pt-14 pb-8">
      <div
        role="progressbar"
        aria-label={t("progress", { step, total: SELL_STEPS })}
        aria-valuemin={1}
        aria-valuemax={SELL_STEPS}
        aria-valuenow={step}
        className="flex gap-1.5"
      >
        {Array.from({ length: SELL_STEPS }, (_, index) => (
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
      <div className="mt-6 flex-1">{children}</div>
      <div className="sticky bottom-0 mt-8 flex flex-col gap-2.5 bg-surface pt-3 pb-2">
        {actions}
      </div>
    </main>
  );
}
