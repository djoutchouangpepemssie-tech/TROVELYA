import { readFile } from "node:fs/promises";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn } from "./session";

const sell = messages.Sell;
const PHOTO = path.join(import.meta.dirname, "..", "e2e-full", "fixtures", "portrait.jpg");

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

const shown = (page: Page) =>
  page.getByRole("list", { name: sell.photos.title }).getByRole("listitem");
const status = (page: Page, text: string) => shown(page).filter({ hasText: text });

// W09, step 1 (P2-T09a1): photos chosen in the gallery, sent and processed (Garage and the
// worker of the e2e stack), ordered, one taken away; then the member may go on.
test("sell, step 1: photos sent, ordered and taken away", async ({ page }) => {
  test.setTimeout(90_000);
  await seller(page);
  await expect(page.getByRole("heading", { level: 1, name: sell.photos.title })).toBeFocused();
  const next = page.getByRole("button", { name: sell.photos.next });
  await expect(next).toBeDisabled();
  await expectNoAxeViolations(page);

  const buffer = await readFile(PHOTO);
  await page.getByLabel(sell.photos.gallery).setInputFiles([
    { name: "robe-face.jpg", mimeType: "image/jpeg", buffer },
    { name: "robe-dos.jpg", mimeType: "image/jpeg", buffer },
  ]);
  await expect(status(page, sell.photos.status.ready)).toHaveCount(2, { timeout: 60_000 });
  await expect(page.getByRole("img", { name: /^Photo 1 : robe-face\.jpg$/ })).toBeVisible();

  await page.getByRole("button", { name: "Reculer la photo 1" }).click();
  await expect(page.getByRole("img", { name: /^Photo 1 : robe-dos\.jpg$/ })).toBeVisible();
  await page.getByRole("button", { name: "Retirer la photo 2" }).click();
  await expect(shown(page)).toHaveCount(1);
  await expect(next).toBeEnabled();
  await expectNoAxeViolations(page);
});

test("sell: a file of another kind is refused, and says why", async ({ page }) => {
  await seller(page);
  await page
    .getByLabel(sell.photos.gallery)
    .setInputFiles([
      { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("pas une photo") },
    ]);
  await expect(page.getByText(sell.photos.failure.type)).toBeVisible();
  await expect(page.getByRole("button", { name: sell.photos.next })).toBeDisabled();
});

test("sell: a member without a completed profile is told how to sell", async ({ page }) => {
  await signIn(page, { completed: false });
  await page.goto("/fr/vendre");
  await expect(page.getByText(sell.refused.incomplete)).toBeVisible();
  await expect(page.getByRole("link", { name: sell.refused.complete })).toHaveAttribute(
    "href",
    "/fr/bienvenue",
  );
});
