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

async function newMember(browser: import("@playwright/test").Browser) {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL ?? "" });
  const page = await context.newPage();
  await signIn(page, { completed: true });
  await page.goto("/fr");
  return { context, page, ...(await me(page)) };
}

test("block asks first, then focus and announcement follow the change", async ({
  page,
  browser,
}) => {
  const other = await newMember(browser);
  await signIn(page, { completed: true });
  await page.goto(`/fr/u/${other.username}`);
  await page.getByRole("button", { name: p.block }).click();
  const dialog = page.getByRole("dialog", {
    name: p.blockTitle.replace("{name}", other.display_name),
  });
  await expect(dialog).toBeVisible();
  await expectNoAxeViolations(page);
  await dialog.getByRole("button", { name: p.blockConfirm }).click();
  const unblock = page.getByRole("button", { name: p.unblock });
  await expect(unblock).toBeFocused();
  await expect(page.getByRole("status")).toHaveText(
    p.done.blocked.replace("{name}", other.display_name),
  );
  await expect(page.getByRole("button", { name: p.follow })).toHaveCount(0);
  await unblock.click();
  await expect(page.getByRole("button", { name: p.follow })).toBeFocused();
  await expect(page.getByRole("status")).toHaveText(
    p.done.unblocked.replace("{name}", other.display_name),
  );
  await other.context.close();
});

test("unfollow says what it does, and an offline click shows a message", async ({
  page,
  browser,
}) => {
  const other = await newMember(browser);
  await signIn(page, { completed: true });
  await page.goto(`/fr/u/${other.username}`);
  await page.getByRole("button", { name: p.follow }).click();
  const unfollow = page.getByRole("button", { name: p.unfollowLabel });
  await expect(unfollow).toBeFocused();
  await unfollow.click();
  await expect(page.getByRole("button", { name: p.follow })).toBeVisible();
  // Network down: a French message in place, not the error page.
  await page.route("**/api/v1/users/*/follow", (route) => route.abort());
  await page.getByRole("button", { name: p.follow }).click();
  await expect(page.getByRole("alert").filter({ hasText: p.error })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: other.display_name })).toBeVisible();
  await other.context.close();
});

test("a pseudo taken by someone else is refused on the field", async ({ page, browser }) => {
  const other = await newMember(browser);
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await page.getByLabel(a.profile.username).fill(other.username);
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: a.profile.errors.usernameTaken }),
  ).toBeVisible();
  await expect(page.getByLabel(a.profile.username)).toBeFocused();
  await other.context.close();
});

test("a profile changed elsewhere keeps what was typed and saves on the second try", async ({
  page,
}) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await expect(page.getByLabel(a.profile.displayName)).toBeEnabled();
  // Another tab saves first: the version this form holds is now stale.
  await page.evaluate(async () => {
    await fetch("/api/v1/csrf");
    const current = (await (await fetch("/api/v1/me")).json()) as { version: number };
    const csrf = document.cookie.match(/__Host-trv_csrf=([^;]+)/)?.[1] ?? "";
    await fetch("/api/v1/me", {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        "if-match": String(current.version),
        "x-csrf-token": csrf,
      },
      body: JSON.stringify({ bio: "Écrit dans un autre onglet" }),
    });
  });
  await page.getByLabel(a.profile.bio).fill("Mon texte à moi");
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(page.getByRole("alert").filter({ hasText: a.profile.errors.stale })).toBeVisible();
  await expect(page.getByLabel(a.profile.bio)).toHaveValue("Mon texte à moi");
  await page.getByRole("button", { name: a.profile.save }).click();
  await expect(page.getByRole("status")).toContainText(a.profile.saved);
  const bio = await page.evaluate(
    async () => ((await (await fetch("/api/v1/me")).json()) as { bio: string }).bio,
  );
  expect(bio).toBe("Mon texte à moi");
});

test("two quick feed changes are both kept", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  const personalised = page.getByRole("switch", { name: a.feed.personalised });
  const before = (await personalised.getAttribute("aria-checked")) === "true";
  // Slow the API so the second change happens while the first request is in flight.
  await page.route("**/api/v1/me/preferences", async (route) => {
    if (route.request().method() === "PUT")
      await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await personalised.click();
  await page.getByLabel(a.feed.discovery).fill("90");
  await expect(page.getByRole("status")).toContainText(a.feed.saved, { timeout: 10_000 });
  await page.unroute("**/api/v1/me/preferences");
  const stored = await page.evaluate(async () => {
    const response = await fetch("/api/v1/me/preferences");
    return (await response.json()) as { personalised_feed: boolean; feed_discovery_level: number };
  });
  expect(stored).toEqual(
    expect.objectContaining({ personalised_feed: !before, feed_discovery_level: 90 }),
  );
});

test("leaving right after moving the slider still saves it", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await page.getByLabel(a.feed.discovery).fill("20");
  await page.getByRole("link", { name: a.back }).click();
  await expect(page).toHaveURL(/\/fr\/compte$/);
  await expect
    .poll(async () =>
      page.evaluate(async () => {
        const response = await fetch("/api/v1/me/preferences");
        return ((await response.json()) as { feed_discovery_level: number }).feed_discovery_level;
      }),
    )
    .toBe(20);
});

test("unknown pages are in French, and a profile has one address", async ({ page }) => {
  const response = await page.goto("/fr/cette-page-n-existe-pas");
  expect(response?.status()).toBe(404);
  await expect(
    page.getByRole("heading", { level: 1, name: messages.Errors.notFoundTitle }),
  ).toBeVisible();
  await signIn(page, { completed: true });
  await page.goto("/fr");
  const { username } = await me(page);
  await page.goto(`/fr/u/${username.toUpperCase()}`);
  await expect(page).toHaveURL(new RegExp(`/fr/u/${username.replace(/\./g, "\\.")}$`));
});
