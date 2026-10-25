"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { useStepUp } from "@/components/StepUp";
import { authApi } from "@/lib/auth";

import { AccountShell } from "../../AccountShell";
import { EmailSection } from "./EmailSection";
import { PasskeysSection } from "./PasskeysSection";
import { SessionsSection } from "./SessionsSection";

/** One status line and one step-up dialog for the whole page. */
export function SecuritySettings() {
  const t = useTranslations("Account.security");
  const [notice, setNotice] = useState("");
  const [passkeys, setPasskeys] = useState(false);
  const stepUp = useStepUp();

  // Members manage passkeys only while the feature is open to them (auth.passkeys).
  useEffect(() => {
    void authApi.methods().then((methods) => {
      setPasskeys(methods?.passkey ?? false);
    });
  }, []);

  return (
    <AccountShell title={t("title")}>
      <EmailSection stepUp={stepUp.run} onDone={setNotice} />
      <SessionsSection onDone={setNotice} />
      {passkeys && <PasskeysSection stepUp={stepUp.run} onDone={setNotice} />}
      {stepUp.dialog}
      <div role="status" className="sticky bottom-20 md:bottom-4">
        {notice && (
          <p className="rounded-lg bg-ink px-4 py-3 text-sm font-medium text-surface shadow-lg">
            {notice}
          </p>
        )}
      </div>
    </AccountShell>
  );
}
