import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { listingInReview, signIn, signInAsStaff } from "./session";

const t = messages.StaffModeration;

/** The queue is shared with the other tests: each one acts on its own listing (unique title). */
async function openQueue(page: Page, title: string) {
  await signInAsStaff(page, messages.StaffEnrolment);
  await page.goto("/fr/staff/moderation");
  await expect(page.getByRole("heading", { level: 1, name: t.title })).toBeVisible();
  const card = page.getByRole("article", { name: title });
  await expect(card).toBeVisible();
  return card;
}

test("staff moderation: approving a listing puts it online", async ({ page }) => {
  const listing = await listingInReview(page);
  const card = await openQueue(page, listing.title);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);

  await expect(card.getByText("Armes et munitions")).toBeVisible();
  await expect(card.getByText(/^Soumise le \d{2}\/\d{2}\/\d{4}/)).toBeVisible();
  await card.getByRole("button", { name: t.approve }).click();
  await expect(page.getByRole("main").getByRole("status")).toHaveText(
    t.done.active.replace("{title}", listing.title),
  );
  await expect(card).toHaveCount(0);

  const online = await page.request.get(`/api/v1/listings/${listing.id}`);
  expect(online.status()).toBe(200);
  expect(((await online.json()) as { status: string }).status).toBe("active");
});

test("staff moderation: a rejection needs a reason, then takes the listing down", async ({
  page,
}) => {
  const listing = await listingInReview(page);
  const card = await openQueue(page, listing.title);

  await card.getByRole("button", { name: t.reject }).click();
  await card.getByRole("button", { name: t.confirmReject }).click();
  await expect(card.getByRole("alert")).toHaveText(t.errors.reason_required);

  await card.getByRole("combobox", { name: t.reason }).click();
  await page.getByRole("option", { name: "Autre motif" }).click();
  await card.getByRole("button", { name: t.confirmReject }).click();
  await expect(card.getByRole("alert")).toHaveText(t.errors.text_required);

  await card.getByRole("textbox", { name: t.reasonText }).fill("Objet réel, non une réplique");
  await card.getByRole("button", { name: t.confirmReject }).click();
  await expect(page.getByRole("main").getByRole("status")).toHaveText(
    t.done.removed.replace("{title}", listing.title),
  );
  expect((await page.request.get(`/api/v1/listings/${listing.id}`)).status()).toBe(404);
});

test("the moderation queue is refused to visitors and members", async ({ page }) => {
  await page.goto("/fr/staff/moderation");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(t.errors.unauthenticated);
  await signIn(page, { completed: true });
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(t.errors.forbidden);
});
