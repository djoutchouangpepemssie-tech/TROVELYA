import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { signIn } from "./session";

const t = messages.Onboarding;

function uniqueUsername(): string {
  return `e2e_${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

async function completeProfile(page: Page, birthYear = "1990"): Promise<void> {
  await page.getByLabel(t.profile.username).fill(uniqueUsername());
  await page.getByLabel(t.profile.displayName).fill("Arcel D.");
  await page.getByLabel(t.profile.birthYear).fill(birthYear);
  await page.getByRole("checkbox", { name: t.profile.terms }).check();
  await page.getByRole("button", { name: t.profile.submit }).click();
}

test("onboarding complete: profile, interests, 5 km zone, notifications", async ({ page }) => {
  await signIn(page);
  await page.goto("/fr/bienvenue");

  // Step 1: profile (required).
  await expect(page.getByRole("heading", { level: 1, name: t.profile.title })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  await expect(page.getByLabel(t.profile.username)).not.toHaveValue("");
  await expectNoAxeViolations(page);
  await completeProfile(page);

  // Step 2: interests.
  await expect(page.getByRole("heading", { level: 1, name: t.interests.title })).toBeFocused();
  await expectNoAxeViolations(page);
  const mode = page.getByRole("button", { name: t.universes.mode });
  await mode.click();
  await expect(mode).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: t.universes.collection }).click();
  await page.getByRole("button", { name: "Continuer · 2 choisis" }).click();

  // Step 3: zone (5 km by default) and sizes.
  await expect(page.getByRole("heading", { level: 1, name: t.zone.title })).toBeVisible();
  await page.getByLabel(t.zone.search).fill("lyon");
  await page.getByRole("button", { name: /Lyon 7e/ }).click();
  await expect(page.getByText("Lyon 7e · rayon 5 km")).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByLabel(t.zone.shoeSize).fill("42");
  await page.getByRole("button", { name: t.continue }).click();

  // Step 4: e-mail notifications.
  await expect(page.getByRole("heading", { level: 1, name: t.notifications.title })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole("switch", { name: t.notifications.priceDrop }).click();
  await page.getByRole("button", { name: t.notifications.finish }).click();
  await expect(page).toHaveURL(/\/fr$/);

  // Everything was saved through the API.
  const zones = (await (await page.request.get("/api/v1/me/zones")).json()) as {
    data: { place_name: string; radius_km: number; is_default: boolean }[];
  };
  expect(zones.data).toEqual([
    expect.objectContaining({ place_name: "Lyon 7e", radius_km: 5, is_default: true }),
  ]);
  const preferences = (await (await page.request.get("/api/v1/me/preferences")).json()) as {
    interests: string[];
    sizes: Record<string, string>;
    notification_settings: { email?: Record<string, boolean> };
  };
  expect(preferences.interests).toEqual(["mode", "collection"]);
  expect(preferences.sizes).toEqual({ shoe_eu: "42" });
  expect(preferences.notification_settings.email).toEqual({
    new_message: true,
    price_drop: true,
    nearby_new: false,
  });
});

test("onboarding skip optional steps", async ({ page }) => {
  await signIn(page);
  await page.goto("/fr/bienvenue");
  await completeProfile(page);
  for (const title of [t.interests.title, t.zone.title, t.notifications.title]) {
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await page.getByRole("button", { name: t.skip }).click();
  }
  await expect(page).toHaveURL(/\/fr$/);
  const me = (await (await page.request.get("/api/v1/me")).json()) as {
    profile_completed: boolean;
  };
  expect(me.profile_completed).toBe(true);
  const zones = (await (await page.request.get("/api/v1/me/zones")).json()) as { data: [] };
  expect(zones.data).toEqual([]);
});

test("profile step required: no skip, errors announced", async ({ page }) => {
  await signIn(page);
  await page.goto("/fr/bienvenue");
  await expect(page.getByRole("button", { name: t.skip })).toHaveCount(0);
  await expect(page.getByLabel(t.profile.username)).not.toHaveValue("");
  await page.getByLabel(t.profile.username).fill("");
  await page.getByRole("button", { name: t.profile.submit }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: t.profile.usernameInvalid }),
  ).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: t.profile.termsRequired })).toBeVisible();
  await expect(page.getByLabel(t.profile.username)).toBeFocused();
  await expect(page.getByRole("heading", { level: 1, name: t.profile.title })).toBeVisible();
});

test("too young message, and nothing is kept", async ({ page }) => {
  await signIn(page);
  await page.goto("/fr/bienvenue");
  await completeProfile(page, "2014");
  await expect(
    page.getByRole("heading", { level: 1, name: t.profile.tooYoungTitle }),
  ).toBeVisible();
  await expect(page.getByText(t.profile.tooYoungBody)).toBeVisible();
  expect((await page.request.get("/api/v1/me")).status()).toBe(401);
});

test("keyboard only: interests toggle with Space and focus follows the steps", async ({ page }) => {
  await signIn(page, { completed: true });
  // Slow preferences: the step must not be usable before they are loaded (CI race).
  await page.route("**/api/v1/me/preferences", async (route) => {
    if (route.request().method() === "GET") await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await page.goto("/fr/bienvenue");
  const heading = page.getByRole("heading", { level: 1, name: t.interests.title });
  await expect(heading).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: t.universes.mode })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: t.universes.mode })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Continuer · 1 choisi" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: t.zone.title })).toBeFocused();
});

test("signed-out visitors are sent to the home page", async ({ page }) => {
  await page.goto("/fr/bienvenue");
  await expect(page).toHaveURL(/\/fr$/);
});
