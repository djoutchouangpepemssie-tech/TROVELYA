import { Avatar } from "@trovelya/ui";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";
import { cache } from "react";

import { initials } from "@/lib/initials";
import { serverGet } from "@/lib/server-api";

import { ProfileActions } from "./ProfileActions";

export type PublicProfile = {
  id: string;
  username: string;
  display_name: string;
  bio: string | null;
  member_since: string;
  followers_count: number;
  following_count: number;
  viewer: { following: boolean; blocking: boolean } | null;
};

type Props = { params: Promise<{ locale: string; pseudo: string }> };

// Pseudo format (3 to 30 characters): anything else cannot be a member, no API call.
const USERNAME = /^[a-z0-9._]{3,30}$/i;

/** One API call per request, shared by the metadata and the page. */
const loadProfile = cache(async (pseudo: string): Promise<PublicProfile | null> => {
  if (!USERNAME.test(pseudo)) return null;
  const response = await serverGet(["users", pseudo]);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`public profile: ${String(response.status)}`);
  return (await response.json()) as PublicProfile;
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { pseudo } = await params;
  const profile = await loadProfile(decodeURIComponent(pseudo));
  const t = await getTranslations("PublicProfile");
  return {
    // Q13 (P1): no listing and no review yet, so no profile is worth indexing.
    robots: { index: false, follow: false },
    ...(profile
      ? { title: t("metaTitle", { name: profile.display_name, username: profile.username }) }
      : {}),
  };
}

/** W08 (P1 part, Q13): pseudo, name, initials, bio, member since and counters. No place. */
export default async function PublicProfilePage({ params }: Props) {
  const { locale, pseudo } = await params;
  const profile = await loadProfile(decodeURIComponent(pseudo));
  if (!profile) notFound();
  const t = await getTranslations("PublicProfile");
  const format = await getFormatter();
  const since = format.dateTime(new Date(profile.member_since), { month: "long", year: "numeric" });

  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-6 px-4 py-10">
      <div className="flex items-center gap-4">
        <Avatar name={profile.display_name} initials={initials(profile.display_name)} size={72} />
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{profile.display_name}</h1>
          <p className="truncate text-ink-2">@{profile.username}</p>
          <p className="text-sm text-ink-2">{t("memberSince", { date: since })}</p>
        </div>
      </div>
      {profile.bio && <p className="whitespace-pre-line">{profile.bio}</p>}
      <p className="flex gap-4 text-sm text-ink-2" aria-label={t("statsLabel")}>
        <span>{t("followers", { count: profile.followers_count })}</span>
        <span>{t("followingCount", { count: profile.following_count })}</span>
      </p>
      <ProfileActions
        locale={locale}
        userId={profile.id}
        username={profile.username}
        displayName={profile.display_name}
        viewer={profile.viewer}
      />
    </main>
  );
}
