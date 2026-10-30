import path from "node:path";

import { expect, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn } from "./session";

const avatar = messages.Account.profile.avatar;
const PHOTO = path.join(import.meta.dirname, "..", "e2e-full", "fixtures", "portrait.jpg");

// P2-T09a0: the e2e stack stores and processes photos (Garage and the arq worker), as the
// screens that send them (W09) need: a photo sent from the browser comes back processed.
test("a photo sent from the browser is stored and processed", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres");
  await postAsMember(page, "/v1/_test/flag-allow", { key: "media.uploads" });
  await page.reload();
  await page.locator('input[type="file"]').setInputFiles(PHOTO);
  await expect(page.getByText(avatar.preview)).toBeVisible({ timeout: 60_000 });
  // Served by Garage's public variants, as the CSP allows.
  const shown = page.getByRole("group", { name: avatar.label }).locator("img");
  await expect
    .poll(() => shown.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);
});
