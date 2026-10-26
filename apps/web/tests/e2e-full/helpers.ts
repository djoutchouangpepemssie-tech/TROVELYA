import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };

const MAILPIT = `http://127.0.0.1:${process.env.FULL_MAILPIT_PORT ?? "8125"}`;

export async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

type MailpitSummary = { ID: string; Subject: string };

/** The sign-in link of the e-mail the worker delivered to Mailpit, as a path on this site. */
export async function linkFromMailpit(page: Page, email: string): Promise<string> {
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

/** A member signed up by e-mail, profile completed (the rest of onboarding skipped). */
export async function completedMember(page: Page, displayName: string): Promise<void> {
  const auth = messages.Auth;
  const profile = messages.Onboarding.profile;
  const id = Date.now().toString(36);
  const email = `membre-${id}@example.org`;
  await page.goto("/fr/inscription");
  await page.getByLabel(auth.emailLabel).fill(email);
  await page.getByRole("button", { name: auth.emailSubmitSignUp }).click();
  await expect(page.getByRole("status")).toContainText(auth.sent);
  await page.goto(await linkFromMailpit(page, email));
  await page.getByRole("button", { name: auth.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr\/bienvenue$/);
  await page.getByLabel(profile.username).fill(`membre_${id}`);
  await page.getByLabel(profile.displayName).fill(displayName);
  await page.getByLabel(profile.birthYear).fill("1990");
  await page.getByRole("checkbox", { name: profile.terms }).check();
  await page.getByRole("button", { name: profile.submit }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: messages.Onboarding.interests.title }),
  ).toBeVisible();
}
