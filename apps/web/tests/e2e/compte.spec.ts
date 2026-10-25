import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { signIn } from "./session";

const a = messages.Account;
const p = messages.PublicProfile;

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

async function me(page: Page): Promise<{ username: string; display_name: string }> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/me");
    return (await response.json()) as { username: string; display_name: string };
  });
}

test("account hub lists the settings pages", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte");
  await expect(page.getByRole("heading", { level: 1, name: a.title })).toBeVisible();
  const nav = page.getByRole("navigation", { name: a.navLabel });
  for (const name of [a.nav.profile]) {
    await expect(nav.getByRole("link", { name: new RegExp(`^${name}`) })).toBeVisible();
  }
  await expectNoAxeViolations(page);
});

test("edit profile", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await expect(page.getByRole("heading", { level: 1, name: a.profile.title })).toBeVisible();
  await expectNoAxeViolations(page);
  const username = `e2e_${Date.now().toString(36)}`;
  await page.getByLabel(a.profile.username).fill(username);
  await page.getByLabel(a.profile.displayName).fill("Lucie Martin");
  await page.getByLabel(a.profile.bio).fill("Collectionneuse de lampes opalines.");
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(page.getByRole("status")).toContainText(a.profile.saved);
  expect(await me(page)).toMatchObject({ username, display_name: "Lucie Martin" });
  // Saving again works: the form keeps the new version (If-Match).
  await page.getByLabel(a.profile.displayName).fill("Lucie M.");
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(page.getByRole("status")).toContainText(a.profile.saved);
  expect((await me(page)).display_name).toBe("Lucie M.");
});

test("profile form refuses an invalid username", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await page.getByLabel(a.profile.username).fill("A b");
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: a.profile.errors.usernameFormat }),
  ).toBeVisible();
  await expect(page.getByLabel(a.profile.username)).toBeFocused();
});

test("feed preferences are saved", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  const personalised = page.getByRole("switch", { name: a.feed.personalised });
  await expect(personalised).toBeVisible();
  const before = await personalised.getAttribute("aria-checked");
  await personalised.click();
  await expect(page.getByRole("status")).toContainText(a.feed.saved);
  const stored = await page.evaluate(async () => {
    const response = await fetch("/api/v1/me/preferences");
    return ((await response.json()) as { personalised_feed: boolean }).personalised_feed;
  });
  expect(String(stored)).not.toBe(before);
});

test("public profile shows no location and can be followed", async ({ page, browser }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr");
  const owner = await me(page);
  // Signed out: the public profile is readable, without any place.
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL ?? "" });
  const visitor = await context.newPage();
  await visitor.goto(`/fr/u/${owner.username}`);
  await expect(visitor.getByRole("heading", { level: 1, name: owner.display_name })).toBeVisible();
  await expect(visitor.getByText(`@${owner.username}`)).toBeVisible();
  await expect(visitor.getByText(/^Membre depuis \p{L}+ \d{4}$/u)).toBeVisible();
  await expect(visitor.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expectNoAxeViolations(visitor);
  // A signed-in member follows them.
  await signIn(visitor, { completed: true });
  await visitor.reload();
  await visitor.getByRole("button", { name: p.follow }).click();
  await expect(visitor.getByRole("button", { name: p.following })).toBeVisible();
  await expect(visitor.getByText("1 abonné", { exact: true })).toBeVisible();
  await context.close();
  // One's own profile offers the settings, not "follow".
  await page.goto(`/fr/u/${owner.username}`);
  await expect(page.getByRole("link", { name: p.edit })).toBeVisible();
  await expect(page.getByRole("button", { name: p.follow })).toHaveCount(0);
});

test("unknown member gives a 404 page", async ({ page }) => {
  const response = await page.goto("/fr/u/personne_inconnue_42");
  expect(response?.status()).toBe(404);
  // A malformed escape is refused cleanly, never a server error.
  expect((await page.goto("/fr/u/%E0"))?.status()).toBe(400);
});

test("settings send signed-out visitors to the sign-in page", async ({ page }) => {
  await page.goto("/fr/compte/parametres");
  await expect(page).toHaveURL(/\/fr\/connexion\?suivant=%2Ffr%2Fcompte%2Fparametres$/);
});
