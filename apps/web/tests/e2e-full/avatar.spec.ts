import path from "node:path";

import { expect, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { completedMember, expectNoAxeViolations } from "./helpers";

const avatar = messages.Account.profile.avatar;
const PHOTO = path.join(import.meta.dirname, "fixtures", "portrait.jpg");

// P2-T02c: the photo goes from the browser straight to storage (Garage, as R2), the worker
// checks it and crops it square, the member confirms it, the header shows it.
test("profile photo: choose, preview, save, shown in the header", async ({ page }) => {
  const name = "Lucie Photo";
  await completedMember(page, name);
  await page.goto("/fr/compte/parametres");
  await expect(page.getByRole("group", { name: avatar.label })).toBeVisible();
  await expectNoAxeViolations(page);

  await page.locator('input[type="file"]').setInputFiles(PHOTO);
  await expect(page.getByText(avatar.preview)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: avatar.save }).click();
  await expect(page.getByRole("status")).toContainText(avatar.saved);

  // The header shows the photo, loaded from the public variants (CSP and storage allow it).
  const photo = page.getByRole("banner").getByRole("img", { name });
  await expect(photo).toBeVisible();
  await expect
    .poll(() => photo.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);
  await expectNoAxeViolations(page);

  // What the API stored: square variants, 320 and 640 pixels, AVIF and WebP.
  const me = (await (await page.request.get("/api/v1/me")).json()) as {
    avatar: { format: string; width: number; height: number }[];
  };
  expect(me.avatar.map((v) => `${v.format} ${String(v.width)}x${String(v.height)}`).sort()).toEqual(
    ["avif 320x320", "avif 640x640", "webp 320x320", "webp 640x640"],
  );

  // Removed: the initials come back.
  await page.getByRole("button", { name: avatar.remove }).click();
  await expect(page.getByRole("status")).toContainText(avatar.removed);
  await expect(page.getByRole("banner").getByRole("img", { name })).toHaveCount(0);
});
