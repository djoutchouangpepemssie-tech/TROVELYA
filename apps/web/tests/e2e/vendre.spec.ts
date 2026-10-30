import { readFile } from "node:fs/promises";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { devices, expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn } from "./session";

const sell = messages.Sell;
const photos = sell.photos;
const details = sell.details;
const PHOTO = path.join(import.meta.dirname, "..", "e2e-full", "fixtures", "portrait.jpg");

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

async function pick(page: Page, names: string[]): Promise<void> {
  const buffer = await readFile(PHOTO);
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: photos.gallery }).click();
  await (await chooser).setFiles(names.map((name) => ({ name, mimeType: "image/jpeg", buffer })));
}

const label = (key: "start" | "end" | "remove", position: number) =>
  photos[key].replace("{position}", String(position));
const cards = (page: Page) => page.getByRole("list", { name: photos.title }).getByRole("listitem");

// W09, step 1 (P2-T09a1): photos chosen in the gallery, sent and processed (Garage and the
// worker of the e2e stack), ordered and taken away by keyboard, the focus kept; then onwards.
test("sell, step 1: photos sent, ordered and taken away by keyboard", async ({ page }) => {
  test.setTimeout(90_000);
  await seller(page);
  await expect(page.getByRole("heading", { level: 1, name: photos.title })).toBeFocused();
  const next = page.getByRole("button", { name: photos.next });
  await expect(next).toBeDisabled();
  await expect(next).toBeInViewport(); // never under the tab bar
  await expectNoAxeViolations(page);

  await pick(page, ["robe-face.jpg", "robe-dos.jpg"]);
  await expect(cards(page).filter({ hasText: photos.status.ready })).toHaveCount(2, {
    timeout: 60_000,
  });
  await page.getByRole("button", { name: label("end", 1) }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("img", { name: /^Photo 1 : robe-dos\.jpg$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: label("start", 2) })).toBeFocused();
  await page.getByRole("button", { name: label("remove", 2) }).focus();
  await page.keyboard.press("Enter");
  await expect(cards(page)).toHaveCount(1);
  await expect(page.getByRole("button", { name: label("remove", 1) })).toBeFocused();
  await expect(next).toBeEnabled();
  await expectNoAxeViolations(page);
});

async function toDetails(page: Page): Promise<void> {
  await pick(page, ["robe-face.jpg"]);
  await expect(cards(page).filter({ hasText: photos.status.ready })).toHaveCount(1, {
    timeout: 60_000,
  });
  await page.getByRole("button", { name: photos.next }).click();
}

// W09, step 2 (P2-T09a2b2): the fake AI's dress fills the fields, marked as proposed; a field
// the API would refuse says so and takes the focus; then onwards.
test("sell, step 2: the AI's proposal, checked field by field", async ({ page }) => {
  test.setTimeout(90_000);
  await seller(page);
  await postAsMember(page, "/v1/_test/flag-allow", { key: "ai.assist" });
  await toDetails(page);
  await expect(page.getByRole("heading", { level: 1, name: details.title })).toBeFocused({
    timeout: 30_000,
  });
  const title = page.getByRole("textbox", { name: details.titleLabel });
  await expect(title).toHaveValue("Robe en lin bleue");
  await expect(title).toHaveAccessibleDescription(details.proposed);
  await expect(page.getByRole("combobox", { name: details.category })).toHaveValue(
    "mode.femme.robes",
  );
  // A long category's name never widens the page past the phone's screen.
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
  await expectNoAxeViolations(page);

  await title.fill("Robe en lin bleu ciel");
  await expect(title).not.toHaveAccessibleDescription(details.proposed);
  await page.getByRole("button", { name: details.next }).click();
  const description = page.getByRole("textbox", { name: details.description });
  await expect(description).toBeFocused();
  await expect(page.getByText(details.errors.too_short)).toBeVisible();
  await expectNoAxeViolations(page);

  // A category that takes only new items leaves no hidden condition behind, and asks its own
  // questions; the box left unticked answers no.
  const category = page.getByRole("combobox", { name: details.category });
  const condition = page.getByRole("combobox", { name: details.condition });
  await category.selectOption("beaute_bien_etre.soins_maquillage.maquillage");
  await expect(condition).toHaveValue("");
  await expect(
    page.getByRole("checkbox", { name: "Neuf sous emballage scellé" }),
  ).not.toBeChecked();
  await category.selectOption("mode.femme.robes");
  await condition.selectOption("very_good");
  await description.fill("Portée deux fois, aucune tache, taille un peu grand.");
  await page.getByRole("button", { name: details.next }).click();
  await expect(page.getByRole("heading", { level: 1, name: sell.price.title })).toBeFocused();
});

test("sell, step 2: without the AI, the member fills the fields", async ({ page }) => {
  test.setTimeout(90_000);
  await seller(page);
  await toDetails(page);
  await expect(page.getByText(details.ai.unavailable)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("textbox", { name: details.titleLabel })).toHaveValue("");
  await page.getByRole("button", { name: details.next }).click();
  await expect(page.getByRole("textbox", { name: details.titleLabel })).toBeFocused();
  await expectNoAxeViolations(page);
});

test("sell: past 12 photos, the others are not added, and the member is told", async ({ page }) => {
  test.setTimeout(120_000);
  await seller(page);
  await pick(
    page,
    Array.from({ length: 13 }, (_, i) => `photo-${String(i)}.jpg`),
  );
  await expect(cards(page)).toHaveCount(12);
  await expect(page.getByText("1 photo non ajoutée : 12 au maximum.")).toBeAttached();
  await expect(page.getByRole("button", { name: photos.gallery })).toBeDisabled();
});

test("sell: a file of another kind is refused, and says why", async ({ page }) => {
  await seller(page);
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: photos.gallery }).click();
  await (
    await chooser
  ).setFiles([{ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("pas une photo") }]);
  await expect(cards(page).getByText(photos.failure.type)).toBeVisible();
  await expect(page.getByRole("button", { name: photos.next })).toBeDisabled();
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
