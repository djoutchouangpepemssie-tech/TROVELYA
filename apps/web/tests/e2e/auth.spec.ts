import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { signIn } from "./session";

const t = messages.Auth;
const h = messages.Header;

function uniqueEmail(): string {
  return `e2e-auth-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}@example.org`;
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

/** The link the e-mail would carry (test-only route), as a path on this site. */
async function magicLinkPath(page: Page, email: string, expired = false): Promise<string> {
  const response = await page.request.post("/api/v1/_test/magic-link", {
    data: { email, expired },
  });
  expect(response.ok()).toBe(true);
  const { link } = (await response.json()) as { link: string };
  const url = new URL(link);
  return url.pathname + url.hash;
}

async function meStatus(page: Page): Promise<number> {
  return page.evaluate(async () => (await fetch("/api/v1/me")).status);
}

test("magic link request shows a neutral message", async ({ page }) => {
  await page.goto("/fr/connexion");
  await expect(page.getByRole("heading", { level: 1, name: t.signInTitle })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByLabel(t.emailLabel).fill(uniqueEmail());
  await page.getByRole("button", { name: t.emailSubmitSignIn }).click();
  await expect(page.getByRole("status")).toContainText(t.sent);
  // Focus follows the form that was replaced; the lifetime is the platform setting (15 min).
  await expect(page.getByText(t.sent, { exact: true })).toBeFocused();
  await expect(page.getByRole("status")).toContainText("15 minutes");
  await expectNoAxeViolations(page);
  // Another address can be used.
  await page.getByRole("button", { name: t.otherEmail }).click();
  await expect(page.getByLabel(t.emailLabel)).toBeFocused();
});

test("sign-in shows only the methods that are on", async ({ page }) => {
  await page.goto("/fr/connexion");
  await expect(page.getByLabel(t.emailLabel)).toBeVisible();
  // No "Se connecter" in the header of the sign-in page itself.
  await expect(page.getByRole("banner").getByRole("link", { name: h.signIn })).toHaveCount(0);
  // The e2e stack runs with every flag off: no Google, Apple or passkey button.
  for (const name of [t.google, t.apple, t.passkey]) {
    await expect(page.getByRole("button", { name })).toHaveCount(0);
    await expect(page.getByRole("link", { name })).toHaveCount(0);
  }
});

test("invalid address is refused before sending", async ({ page }) => {
  await page.goto("/fr/inscription");
  await expect(page.getByRole("heading", { level: 1, name: t.signUpTitle })).toBeVisible();
  await page.getByLabel(t.emailLabel).fill("pas-une-adresse");
  await page.getByRole("button", { name: t.emailSubmitSignUp }).click();
  await expect(page.getByRole("alert").filter({ hasText: t.emailInvalid })).toBeVisible();
  await expect(page.getByLabel(t.emailLabel)).toBeFocused();
});

test("verify page requires a click, then a new member goes to onboarding", async ({ page }) => {
  const path = await magicLinkPath(page, uniqueEmail());
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: t.verifyTitle })).toBeVisible();
  await expect(page).toHaveURL(/\/fr\/verifier$/); // the token left the address bar
  await expectNoAxeViolations(page);
  // Opening the link (mail scanners do) does not sign in.
  expect(await meStatus(page)).toBe(401);
  await page.getByRole("button", { name: t.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr\/bienvenue$/);
  expect(await meStatus(page)).toBe(200);
});

test("a completed member goes back to the page they came from", async ({ page, context }) => {
  const { email } = await signIn(page, { completed: true });
  await context.clearCookies();
  await page.goto("/fr/connexion?suivant=%2Ffr%2Fcompte");
  await page.getByLabel(t.emailLabel).fill(email);
  await page.getByRole("button", { name: t.emailSubmitSignIn }).click();
  await expect(page.getByRole("status")).toContainText(t.sent);
  await page.goto(await magicLinkPath(page, email));
  await page.getByRole("button", { name: t.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr\/compte$/);
});

test("an outside return address is ignored", async ({ page, context }) => {
  const { email } = await signIn(page, { completed: true });
  await context.clearCookies();
  await page.goto("/fr/connexion?suivant=https%3A%2F%2Fevil.example%2F");
  await page.getByLabel(t.emailLabel).fill(email);
  await page.getByRole("button", { name: t.emailSubmitSignIn }).click();
  await expect(page.getByRole("status")).toContainText(t.sent);
  await page.goto(await magicLinkPath(page, email));
  await page.getByRole("button", { name: t.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr$/);
});

test("expired link shows an error and a way to get a new one", async ({ page }) => {
  await page.goto(await magicLinkPath(page, uniqueEmail(), true));
  await page.getByRole("button", { name: t.verifySubmit }).click();
  await expect(page.getByRole("alert").filter({ hasText: t.verifyInvalid })).toBeVisible();
  await expectNoAxeViolations(page); // error text keeps its contrast
  await page.getByRole("link", { name: t.verifyResend }).click();
  await expect(page).toHaveURL(/\/fr\/connexion$/);
  expect(await meStatus(page)).toBe(401);
});

test("header shows the account menu when signed in, and signs out", async ({ page }) => {
  await page.goto("/fr");
  const header = page.getByRole("banner");
  await expect(header.getByRole("link", { name: h.signIn })).toBeVisible();

  await signIn(page, { completed: true });
  await page.goto("/fr");
  const menuButton = header.getByRole("button", { name: h.accountMenu });
  await expect(menuButton).toBeVisible();
  await expectNoAxeViolations(page);
  // Keyboard: the menu opens on the first item, arrows move, Escape closes on the button.
  await menuButton.focus();
  await page.keyboard.press("Enter");
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("menuitem", { name: h.account })).toBeFocused();
  await expectNoAxeViolations(page);
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: h.signOut })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: h.account })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await expect(menuButton).toBeFocused();

  await menuButton.click();
  await page.getByRole("menuitem", { name: h.signOut }).click();
  await expect(header.getByRole("link", { name: h.signIn })).toBeVisible();
  expect(await meStatus(page)).toBe(401);
});

test("mobile tabs: home and profile, no dead link", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/fr");
  const tabs = page.getByRole("navigation", { name: h.tabsLabel });
  await expect(tabs.getByRole("link")).toHaveCount(2);
  // The end of the page stays reachable above the fixed bar.
  const footer = page.getByRole("navigation", { name: messages.Legal.footerLabel });
  await footer.scrollIntoViewIfNeeded();
  const footerBox = await footer.boundingBox();
  const tabsBox = await tabs.boundingBox();
  expect((footerBox?.y ?? 0) + (footerBox?.height ?? 0)).toBeLessThanOrEqual(tabsBox?.y ?? 0);
  await tabs.getByRole("link", { name: h.profile }).click();
  await expect(page).toHaveURL(/\/fr\/connexion/);

  await signIn(page, { completed: true });
  // Tapped before the session request answers (slowed down here): still the account page.
  await page.route("**/api/v1/me", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.goto("/fr");
  await tabs.getByRole("link", { name: h.profile }).click();
  await expect(page).toHaveURL(/\/fr\/compte$/);
  await page.unroute("**/api/v1/me");
  await expect(page.getByRole("heading", { level: 1, name: messages.Account.title })).toBeVisible();
});

test("keyboard only: the e-mail form is reachable and submits with Enter", async ({ page }) => {
  await page.goto("/fr/connexion");
  const field = page.getByLabel(t.emailLabel);
  for (let i = 0; i < 12 && !(await field.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(field).toBeFocused();
  await page.keyboard.type(uniqueEmail());
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText(t.sent);
});

test("signed-in visitors are sent away from the sign-in page", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/connexion");
  await expect(page).toHaveURL(/\/fr$/);
});

test("a return address with dot segments is ignored", async ({ page, context }) => {
  const { email } = await signIn(page, { completed: true });
  await context.clearCookies();
  await page.goto("/fr/connexion?suivant=%2Ffr%2F..%2Fen%2Fcompte");
  await page.getByLabel(t.emailLabel).fill(email);
  await page.getByRole("button", { name: t.emailSubmitSignIn }).click();
  await expect(page.getByRole("status")).toContainText(t.sent);
  await page.goto(await magicLinkPath(page, email));
  await page.getByRole("button", { name: t.verifySubmit }).click();
  await expect(page).toHaveURL(/\/fr$/);
});

test("switching between sign-in and sign-up keeps the return address", async ({ page }) => {
  await page.goto("/fr/connexion?suivant=%2Ffr%2Fcompte");
  await page.getByRole("link", { name: t.switchToSignUp }).click();
  await expect(page).toHaveURL(/\/fr\/inscription\?suivant=%2Ffr%2Fcompte$/);
  expect(await page.evaluate(() => localStorage.getItem("trv_next"))).toBe("/fr/compte");
});

test("signing out from the account page lands on the home page, nothing kept", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte");
  await page.getByRole("button", { name: messages.Account.signOut }).click();
  await expect(page).toHaveURL(/\/fr$/);
  await expect(page.getByRole("banner").getByRole("link", { name: h.signIn })).toBeVisible();
  expect(await meStatus(page)).toBe(401);
  expect(await page.evaluate(() => localStorage.getItem("trv_next"))).toBeNull();
});

test("the staff area shows no member sign-in link", async ({ page }) => {
  await page.goto("/fr/staff/enrolement");
  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: h.signIn })).toHaveCount(0);
});
