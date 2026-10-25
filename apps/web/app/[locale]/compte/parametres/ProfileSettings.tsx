"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { AccountShell } from "../AccountShell";
import { FeedPreferences } from "./FeedPreferences";
import { ProfileForm } from "./ProfileForm";

/** One status line for the page: what was just saved is announced once. */
export function ProfileSettings() {
  const t = useTranslations("Account.profile");
  const [notice, setNotice] = useState("");
  return (
    <AccountShell title={t("title")}>
      <ProfileForm onSaved={setNotice} />
      <FeedPreferences onSaved={setNotice} />
      {/* Always mounted, so screen readers announce each new message; shown near the bottom. */}
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
