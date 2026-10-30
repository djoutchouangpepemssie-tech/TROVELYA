import AxeBuilder from "@axe-core/playwright";
import { devices, expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn } from "./session";

const sell = messages.Sell;
const photos = sell.photos;

// Mobile first (plan P2-T09a): a phone, in Chromium.
test.use({ ...devices["Pixel 7"] });

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.map((v) => v.id)).toEqual([]);
}

async function seller(page: Page): Promise<void> {
  await signIn(page, { completed: true });
  await page.goto("/fr/vendre");
  await postAsMember(page, "/v1/_test/flag-allow", { key: "media.uploads" });
  await page.reload();
}

// W09 (P2-T09a1a): a member who may sell lands on the first step, its title focused, on a
// phone without the tab bar (the steps' actions stay in view).
test("sell: a member who may sell starts with the photos", async ({ page }) => {
  await seller(page);
  await expect(page.getByRole("heading", { level: 1, name: photos.title })).toBeFocused();
  await expect(page.getByRole("navigation", { name: messages.Header.tabsLabel })).toHaveCount(0);
  await expectNoAxeViolations(page);
});

test("sell: a member without a completed profile is told how to sell", async ({ page }) => {
  await signIn(page, { completed: false });
  await page.goto("/fr/vendre");
  await expect(page.getByText(sell.refused.incomplete)).toBeVisible();
  await expect(page.getByRole("link", { name: sell.refused.complete })).toHaveAttribute(
    "href",
    "/fr/bienvenue",
  );
  await expectNoAxeViolations(page);
});
