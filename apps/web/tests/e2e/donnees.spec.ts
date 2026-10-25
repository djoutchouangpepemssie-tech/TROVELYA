import { readFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn, sitePath } from "./session";

const data = messages.Account.data;
const privacy = messages.Account.privacy;
const notice = messages.ErasureNotice;
const step = messages.StepUp;

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

async function meStatus(page: Page): Promise<number> {
  return page.evaluate(async () => (await fetch("/api/v1/me")).status);
}

test("the account hub links to privacy and data", async ({ page }) => {
  await signIn(page, { completed: true });
  const hub = page.getByRole("navigation", { name: messages.Account.navLabel });
  await page.goto("/fr/compte");
  await hub.getByRole("link", { name: new RegExp(messages.Account.nav.privacy) }).click();
  await expect(page).toHaveURL(/\/fr\/compte\/parametres\/confidentialite$/);
  await page.goto("/fr/compte");
  await hub.getByRole("link", { name: new RegExp(messages.Account.nav.data) }).click();
  await expect(page).toHaveURL(/\/fr\/compte\/donnees$/);
});

test("privacy page: nothing to accept today, and a given consent can be withdrawn", async ({
  page,
}) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres/confidentialite");
  await expect(page.getByRole("heading", { level: 1, name: privacy.title })).toBeVisible();
  await expect(page.getByText(privacy.none)).toBeVisible();
  await expectNoAxeViolations(page);

  // The precise location, granted during the welcome steps.
  await postAsMember(page, "/v1/me/consents", {
    purpose: "location",
    granted: true,
    policy_version: "provisoire-2026-10",
  });
  await page.reload();
  const location = page.getByRole("switch", { name: messages.Legal.purposes.location });
  await expect(location).toBeChecked();
  await location.click();
  await expect(page.getByText(privacy.saved)).toBeVisible();
  await expect(location).not.toBeChecked();
  const latest = await page.evaluate(async () => {
    const state = (await (await fetch("/api/v1/me/consents")).json()) as {
      consents: { purpose: string; granted: boolean }[];
    };
    return state.consents.find((c) => c.purpose === "location")?.granted;
  });
  expect(latest).toBe(false);
  await expectNoAxeViolations(page);
});

test("request an export, then download it", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/donnees");
  await expect(page.getByRole("heading", { level: 1, name: data.title })).toBeVisible();
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: data.exportRequest }).click();
  await expect(page.getByRole("status")).toContainText(data.exportRequested);
  // Asked once: no second request while it is being built.
  await expect(page.getByRole("button", { name: data.exportRequest })).toHaveCount(0);

  // The worker's job, then the member comes back to the page.
  await postAsMember(page, "/v1/_test/build-export");
  await page.reload();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: data.download }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^trovelya-export-\d{4}-\d{2}-\d{2}\.zip$/);
  const bytes = await readFile(await file.path());
  expect(bytes.subarray(0, 2).toString()).toBe("PK"); // a ZIP archive
  await expect(page.getByRole("status")).toContainText(data.downloaded);
  await expectNoAxeViolations(page);
});

test("the export asks for a strong proof first", async ({ page }) => {
  await signIn(page, { completed: true, strong: false });
  await page.goto("/fr/compte/donnees");
  await page.getByRole("button", { name: data.exportRequest }).click();
  const dialog = page.getByRole("dialog", { name: step.title });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: data.exportRequest })).toBeFocused();
});

test("request the erasure, then sign in again and cancel it", async ({ page }) => {
  const { email } = await signIn(page, { completed: true });
  await page.goto("/fr/compte/donnees");
  await page.getByRole("button", { name: data.erasureRequest }).click();
  const confirm = page.getByRole("dialog", { name: data.erasureConfirmTitle });
  await expect(confirm).toContainText("30 jours");
  await expectNoAxeViolations(page);
  await confirm.getByRole("button", { name: data.erasureConfirm }).click();

  await expect(page.getByRole("heading", { level: 1, name: data.erasureDoneTitle })).toBeFocused();
  await expect(page.getByRole("status")).toContainText("Votre compte sera supprimé définitivement");
  expect(await meStatus(page)).toBe(401);
  await expectNoAxeViolations(page);

  // Signing in again during the grace period: every page offers to cancel.
  const response = await page.request.post("/api/v1/_test/magic-link", { data: { email } });
  const { link } = (await response.json()) as { link: string };
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: messages.Auth.verifySubmit }).click();
  await expect(page).not.toHaveURL(/verifier/);
  const banner = page.getByRole("region", { name: notice.label });
  await expect(banner).toContainText("Votre compte sera supprimé définitivement le");
  await expectNoAxeViolations(page);
  await banner.getByRole("button", { name: notice.cancel }).click();
  await expect(page.getByRole("status").filter({ hasText: notice.cancelled })).toBeFocused();
  await expectNoAxeViolations(page);
  await page.goto("/fr/compte");
  await expect(page.getByText(notice.cancelled)).toHaveCount(0); // said once, not on every page
  const me = await page.evaluate(
    async () => (await (await fetch("/api/v1/me")).json()) as { erase_at: string | null },
  );
  expect(me.erase_at).toBeNull();
});

async function signInAgain(page: Page, email: string): Promise<void> {
  const response = await page.request.post("/api/v1/_test/magic-link", { data: { email } });
  const { link } = (await response.json()) as { link: string };
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: messages.Auth.verifySubmit }).click();
  await expect(page).not.toHaveURL(/verifier/);
}

test("during the grace period, the data page itself cancels the erasure", async ({ page }) => {
  const { email } = await signIn(page, { completed: true });
  await page.goto("/fr");
  await postAsMember(page, "/v1/me/erasure");
  await signInAgain(page, email);
  await page.goto("/fr/compte/donnees");
  await expect(page.getByText(/^Votre compte sera supprimé le /)).toBeVisible();
  // The page's own button (the notice above offers the same).
  await page.getByRole("main").getByRole("button", { name: data.erasureCancel }).click();
  await expect(page.getByRole("status").filter({ hasText: notice.cancelled })).toBeVisible();
  await expect(page.getByRole("button", { name: data.erasureRequest })).toBeFocused();
  await expect(page.getByRole("region", { name: notice.label })).toHaveCount(0);
});

test("the erasure's strong proof, closed, gives the focus back", async ({ page }) => {
  await signIn(page, { completed: true, strong: false });
  await page.goto("/fr/compte/donnees");
  await page.getByRole("button", { name: data.erasureRequest }).click();
  await page
    .getByRole("dialog", { name: data.erasureConfirmTitle })
    .getByRole("button", { name: data.erasureConfirm })
    .click();
  await expect(page.getByRole("dialog", { name: step.title })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: data.erasureRequest })).toBeFocused();
  expect(await meStatus(page)).toBe(200); // nothing was asked for
});

test("signed out elsewhere: the next action goes to the sign-in page", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/donnees");
  await expect(page.getByRole("button", { name: data.exportRequest })).toBeVisible();
  await page.context().clearCookies();
  await page.getByRole("button", { name: data.exportRequest }).click();
  await expect(page).toHaveURL(/\/fr\/connexion\?suivant=%2Ffr%2Fcompte%2Fdonnees$/);
});
