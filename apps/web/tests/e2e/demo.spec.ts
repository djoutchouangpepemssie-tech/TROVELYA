import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Temporary mock-up demo (app/[locale]/demo/README.md): removed with it.

const PAGES = [
  "/fr/demo",
  "/fr/demo/catalogue",
  "/fr/demo/annonce",
  "/fr/demo/live",
  "/fr/demo/atelier",
];

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

for (const path of PAGES) {
  test(`demo ${path}: marked fictitious, not indexed, accessible, no broken image`, async ({
    page,
  }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByText("Démonstration · données fictives")).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
    // The real site's header and tabs stay out of the mock-up.
    await expect(page.getByRole("navigation", { name: "Navigation principale" })).toHaveCount(0);
    await page.waitForLoadState("networkidle");
    const broken = await page.locator("img").evaluateAll((images) =>
      images
        .filter((image) => {
          const img = image as HTMLImageElement;
          return img.complete && img.naturalWidth === 0;
        })
        .map((image) => (image as HTMLImageElement).src),
    );
    expect(broken).toEqual([]);
    await expectNoAxeViolations(page);
  });
}

test("demo home: feed tabs and favourites work as in the mock-up", async ({ page }) => {
  await page.goto("/fr/demo");
  await expect(page.getByRole("heading", { level: 2, name: "Choisi pour vous" })).toBeVisible();
  await page.getByRole("button", { name: "Près de moi" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Près de chez vous" })).toBeVisible();
  const heart = page.getByRole("button", { name: "Ajouter aux favoris" }).first();
  await heart.click();
  await expect(heart).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/\/fr\/demo$/); // the heart does not open the product
  // The mega-menu opens on a category and closes with Escape.
  await page.getByRole("button", { name: "Maison" }).click();
  await expect(page.getByText("Luminaires d’atelier")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Luminaires d’atelier")).toHaveCount(0);
});

test("demo links stay inside the demo", async ({ page }) => {
  await page.goto("/fr/demo");
  const hrefs = await page
    .locator(".trv-demo a[href]")
    .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
  const outside = hrefs.filter(
    (href) => !href.startsWith("/fr/demo") && !["/fr", "/fr/legal/cookies"].includes(href),
  );
  expect(outside).toEqual([]);
});

test("demo on a phone keeps the page within the screen width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of PAGES) {
    await page.goto(path);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
