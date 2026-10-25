"use client";

import { Button, Input } from "@trovelya/ui";
import { useTranslations } from "next-intl";
import { type SyntheticEvent, useRef, useState } from "react";

import { useSession } from "@/components/SessionProvider";
import { apiCall, type ApiResult } from "@/lib/api";

type StepUp = <T>(action: () => Promise<ApiResult<T>>) => Promise<ApiResult<T>>;

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Change of address (T05c): a link goes to the new address; the current one stays until then. */
export function EmailSection({
  stepUp,
  onDone,
}: {
  stepUp: StepUp;
  onDone: (message: string) => void;
}) {
  const t = useTranslations("Account.security.email");
  const { me } = useSession();
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<"invalid" | "same" | "error" | null>(null);
  const [sending, setSending] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = value.trim();
    const invalid = !EMAIL.test(address);
    const same = !invalid && address.toLowerCase() === me?.email.toLowerCase();
    if (invalid || same) {
      setProblem(invalid ? "invalid" : "same");
      field.current?.focus();
      return;
    }
    setProblem(null);
    onDone("");
    setSending(true);
    const result = await stepUp(() =>
      apiCall<unknown>("/v1/me/email", {
        method: "POST",
        body: JSON.stringify({ new_email: address }),
      }),
    );
    setSending(false);
    if (result.ok) {
      setValue("");
      onDone(t("sent"));
    } else if (result.code !== "step_up_pending" && result.code !== "step_up_cancelled") {
      setProblem("error");
    }
  }

  return (
    <section aria-labelledby="email-title" className="flex flex-col gap-3">
      <h2 id="email-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {me && <p className="text-ink-2">{t("current", { email: me.email })}</p>}
      <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-3">
        <Input
          ref={field}
          label={t("new")}
          type="email"
          autoComplete="email"
          inputMode="email"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
          }}
          {...(problem === "invalid" || problem === "same" ? { error: t(problem) } : {})}
        />
        {problem === "error" && (
          <p role="alert" className="text-sm text-danger-ink">
            {t("error")}
          </p>
        )}
        <Button type="submit" variant="secondary" disabled={sending} className="self-start">
          {t("submit")}
        </Button>
      </form>
    </section>
  );
}
