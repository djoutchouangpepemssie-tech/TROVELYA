import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };

const auth = messages.Auth;
const onboarding = messages.Onboarding;
const MAILPIT = `http://127.0.0.1:${process.env.FULL_MAILPIT_PORT ?? "8125"}`;

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

type MailpitSummary = { ID: string; Subject: string };

/** The sign-in link of the e-mail the worker delivered to Mailpit, as a path on this site. */
async function linkFromMailpit(page: Page, email: string): Promise<string> {
  const search = `${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`;
  let found: MailpitSummary | undefined;
  await expect
    .poll(
      async () => {
        const answer = (await (await page.request.get(search)).json()) as {
          messages: MailpitSummary[];
        };
        found = answer.messages[0];
        return found?.ID;
      },
      { message: "the sign-in e-mail never reached Mailpit", timeout: 30_000 },
    )
    .toBeTruthy();
  const message = (await (
    await page.request.get(`${MAILPIT}/api/v1/message/${found?.ID ?? ""}`)
  ).json()) as { Text: string };
  const link = /https?:\/\/\S+#token=[\w-]+/.exec(message.Text)?.[0];
  expect(link, "no sign-in link in the e-mail").toBeTruthy();
  const url = new URL(link ?? "");
  return url.pathname + url.hash;
}

test("journey 1: sign-up by e-mail, onboarding, 5 km zone, signed-in home", async ({ page }) => {
  const email = `parcours1-${Date.now().toString(36)}@example.org`;

  // Sign-up: the e-mail is sent by the worker, through SMTP, to Mailpit.
  await page.goto("/fr/inscription");
  await expect(page.getByRole("heading", { level: 1, name: auth.signUpTitle })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByLabel(auth.emailLabel).fill(email);
  await page.getByRole("button", { name: auth.emailSubmitSignUp }).click();
  await expect(page.getByRole("status")).toContainText(auth.sent);

  // The link of the e-mail, opened in the same browser: « Me connecter ».
  await page.goto(await linkFromMailpit(page, email));
  await expect(page.getByRole("heading", { level: 1, name: auth.verifyTitle })).toBeVisible();
  await page.getByRole("button", { name: auth.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr\/bienvenue$/);

  // Profile: username, name, birth year 1990, terms.
  await expect(
    page.getByRole("heading", { level: 1, name: onboarding.profile.title }),
  ).toBeVisible();
  await page.getByLabel(onboarding.profile.username).fill(`parcours_${Date.now().toString(36)}`);
  await page.getByLabel(onboarding.profile.displayName).fill("Arcel D.");
  await page.getByLabel(onboarding.profile.birthYear).fill("1990");
  await page.getByRole("checkbox", { name: onboarding.profile.terms }).check();
  await page.getByRole("button", { name: onboarding.profile.submit }).click();

  // Two universes.
  await expect(
    page.getByRole("heading", { level: 1, name: onboarding.interests.title }),
  ).toBeFocused();
  await page.getByRole("button", { name: onboarding.universes.mode }).click();
  await page.getByRole("button", { name: onboarding.universes.collection }).click();
  await page.getByRole("button", { name: "Continuer · 2 choisis" }).click();

  // Zone « Lyon 7e », 5 km by default.
  await expect(page.getByRole("heading", { level: 1, name: onboarding.zone.title })).toBeVisible();
  await page.getByLabel(onboarding.zone.search).fill("lyon");
  await page.getByRole("button", { name: /Lyon 7e/ }).click();
  await expect(page.getByText("Lyon 7e · rayon 5 km")).toBeVisible();
  await page.getByRole("button", { name: onboarding.continue }).click();

  // E-mail notifications as offered, then the signed-in home page.
  await expect(
    page.getByRole("heading", { level: 1, name: onboarding.notifications.title }),
  ).toBeVisible();
  await page.getByRole("button", { name: onboarding.notifications.finish }).click();
  await expect(page).toHaveURL(/\/fr$/);
  await expectNoAxeViolations(page);

  // What the API stored: a completed profile, and one default zone of 5000 m.
  const me = (await (await page.request.get("/api/v1/me")).json()) as {
    email: string;
    profile_completed: boolean;
  };
  expect(me).toEqual(expect.objectContaining({ email, profile_completed: true }));
  const zones = (await (await page.request.get("/api/v1/me/zones")).json()) as {
    data: { place_name: string; radius_km: number; is_default: boolean }[];
  };
  expect(zones.data).toEqual([
    expect.objectContaining({ place_name: "Lyon 7e", is_default: true }),
  ]);
  expect((zones.data[0]?.radius_km ?? 0) * 1000).toBe(5000);
});
