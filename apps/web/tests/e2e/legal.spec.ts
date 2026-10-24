import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { signIn } from "./session";

const t = messages.Legal;
const ESSENTIAL_COOKIE = /^(__Host-trv_.+|NEXT_LOCALE)$/;

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

/** P1 has no active purpose: simulate one, the choices themselves go to the real API. */
async function activatePurposes(page: Page): Promise<void> {
  await page.route("**/api/v1/me/consents", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    await route.fulfill({
      response,
      json: { ...body, active_purposes: ["analytics", "personalised_ads"] },
    });
  });
}

type Consent = { purpose: string; granted: boolean };

/** Read from the page: it carries `__Host-trv_anon` like the visitor's browser does. */
async function savedConsents(page: Page): Promise<Consent[]> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/me/consents");
    return ((await response.json()) as { consents: Consent[] }).consents;
  });
}

for (const [slug, title] of [
  ["cgu", "Conditions générales d'utilisation"],
  ["confidentialite", "Politique de confidentialité"],
  ["cookies", "Politique cookies"],
  ["mentions", "Mentions légales"],
] as const) {
  test(`legal page ${slug}: provisional notice, reachable from the footer`, async ({ page }) => {
    await page.goto("/fr");
    await page
      .getByRole("navigation", { name: t.footerLabel })
      .getByRole("link", { name: t.footer[slug] })
      .click();
    await expect(page).toHaveURL(new RegExp(`/fr/legal/${slug}$`));
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByRole("note")).toHaveText(t.provisional);
    await expectNoAxeViolations(page);
  });
}

test("unknown legal page is a 404", async ({ page }) => {
  const response = await page.goto("/fr/legal/inconnue");
  expect(response?.status()).toBe(404);
});

test("only essential cookies before any choice, and no banner in P1", async ({ page, context }) => {
  await page.goto("/fr");
  await page.goto("/fr/legal/cookies");
  await expect(page.getByText(t.choices.none)).toBeVisible();
  await expect(page.getByRole("region", { name: t.banner.title })).toHaveCount(0);
  const names = (await context.cookies()).map((cookie) => cookie.name);
  for (const name of names) expect(name).toMatch(ESSENTIAL_COOKIE);
  expect(names).not.toContain("__Host-trv_anon"); // set only when a choice is made
});

test("banner: equal buttons, refuse all, then grant and withdraw from the cookie page", async ({
  page,
  context,
}) => {
  await activatePurposes(page);
  await page.goto("/fr");
  const banner = page.getByRole("region", { name: t.banner.title });
  await expect(banner).toBeVisible();
  await expectNoAxeViolations(page);

  const boxes = await Promise.all(
    [t.banner.acceptAll, t.banner.refuseAll, t.banner.customise].map(async (name) =>
      banner.getByRole("button", { name }).boundingBox(),
    ),
  );
  for (const box of boxes) {
    expect(box?.width).toBeCloseTo(boxes[0]?.width ?? 0, 0);
    expect(box?.height).toBeCloseTo(boxes[0]?.height ?? 0, 0);
  }

  await banner.getByRole("button", { name: t.banner.refuseAll }).click();
  await expect(banner).toHaveCount(0);
  expect((await context.cookies()).map((c) => c.name)).toContain("__Host-trv_anon");

  // The choice is remembered on the next page.
  await page.goto("/fr/legal/cookies");
  await expect(page.getByRole("region", { name: t.banner.title })).toHaveCount(0);
  const analytics = page.getByRole("switch", { name: t.purposes.analytics });
  await expect(analytics).toHaveAttribute("aria-checked", "false");
  await analytics.click();
  await expect(page.getByText(t.choices.saved)).toBeVisible();
  await expect(analytics).toHaveAttribute("aria-checked", "true");
  await analytics.click(); // withdrawn in one click
  await expect(analytics).toHaveAttribute("aria-checked", "false");

  expect(await savedConsents(page)).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ purpose: "analytics", granted: false }),
      expect.objectContaining({ purpose: "personalised_ads", granted: false }),
    ]),
  );
});

test("banner: customise one purpose", async ({ page }) => {
  await activatePurposes(page);
  await page.goto("/fr");
  const banner = page.getByRole("region", { name: t.banner.title });
  await banner.getByRole("button", { name: t.banner.customise }).click();
  const dialog = page.getByRole("dialog", { name: t.banner.customiseTitle });
  await dialog.getByRole("switch", { name: t.purposes.personalised_ads }).click();
  await dialog.getByRole("button", { name: t.banner.save }).click();
  // The modal dialog hides the banner from the accessibility tree: wait for it to close.
  await expect(dialog).toHaveCount(0);
  await expect(banner).toHaveCount(0);
  const saved = await savedConsents(page);
  expect(saved.map((c) => [c.purpose, c.granted]).sort()).toEqual([
    ["analytics", false],
    ["personalised_ads", true],
  ]);
});

test("onboarding: 'Utiliser ma position' records the location consent", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 45.746, longitude: 4.843 });
  await signIn(page, { completed: true });
  await page.goto("/fr/bienvenue");
  await page.getByRole("button", { name: messages.Onboarding.skip }).click();
  await page.getByRole("button", { name: messages.Onboarding.zone.useLocation }).click();
  await expect(page.getByText("Lyon 7e · rayon 5 km")).toBeVisible();
  expect(await savedConsents(page)).toEqual([
    expect.objectContaining({ purpose: "location", granted: true }),
  ]);
});
