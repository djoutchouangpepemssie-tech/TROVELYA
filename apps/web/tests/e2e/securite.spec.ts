import AxeBuilder from "@axe-core/playwright";
import { type Browser, expect, type Page, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };
import { postAsMember, signIn, sitePath } from "./session";

const s = messages.Account.security;
const step = messages.StepUp;
const confirm = messages.Account.emailConfirm;

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

async function meEmail(page: Page): Promise<string> {
  return page.evaluate(
    async () => ((await (await fetch("/api/v1/me")).json()) as { email: string }).email,
  );
}

/** The same member signed in on a second device (another browser context, by magic link). */
async function secondDevice(browser: Browser, email: string) {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL ?? "" });
  const page = await context.newPage();
  const response = await page.request.post("/api/v1/_test/magic-link", { data: { email } });
  const { link } = (await response.json()) as { link: string };
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: messages.Auth.verifySubmit }).click();
  await expect(page).not.toHaveURL(/verifier/);
  return { context, page };
}

test("security page lists this device", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr/compte/parametres/securite");
  await expect(page.getByRole("heading", { level: 1, name: s.title })).toBeVisible();
  await expect(page.getByText(s.sessions.current)).toBeVisible();
  // Passkeys are not open to members on this stack: no section, no dead button.
  await expect(page.getByRole("heading", { name: s.passkeys.title })).toHaveCount(0);
  await expectNoAxeViolations(page);
});

test("revoke another session", async ({ page, browser }) => {
  const { email } = await signIn(page, { completed: true });
  const other = await secondDevice(browser, email);
  await page.goto("/fr/compte/parametres/securite");
  const revoke = page.getByRole("button", {
    name: s.sessions.revokeLabel.replace("{device}", s.sessions.unknownDevice),
  });
  await expect(revoke).toHaveCount(1);
  await revoke.click();
  await expect(page.getByRole("status")).toContainText(s.sessions.revoked);
  await expect(revoke).toHaveCount(0);
  expect(await other.page.evaluate(async () => (await fetch("/api/v1/me")).status)).toBe(401);
  // This device is still signed in.
  expect(await page.evaluate(async () => (await fetch("/api/v1/me")).status)).toBe(200);
  await other.context.close();
});

test("sign out of every other device", async ({ page, browser }) => {
  const { email } = await signIn(page, { completed: true });
  const first = await secondDevice(browser, email);
  const second = await secondDevice(browser, email);
  await page.goto("/fr/compte/parametres/securite");
  await page.getByRole("button", { name: s.sessions.revokeOthers }).click();
  await expect(page.getByRole("status")).toContainText(s.sessions.revokedOthers);
  for (const device of [first, second]) {
    expect(await device.page.evaluate(async () => (await fetch("/api/v1/me")).status)).toBe(401);
    await device.context.close();
  }
});

test("changing the e-mail asks for a strong proof, by link, then sends the confirmation", async ({
  page,
}) => {
  await signIn(page, { completed: true, strong: false });
  await page.goto("/fr/compte/parametres/securite");
  const newEmail = `e2e-new-${Date.now().toString(36)}@example.org`;
  await page.getByLabel(s.email.new).fill(newEmail);
  await page.getByRole("button", { name: s.email.submit }).click();

  const dialog = page.getByRole("dialog", { name: step.title });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: step.passkey })).toHaveCount(0);
  await expectNoAxeViolations(page);
  await dialog.getByRole("button", { name: step.link }).click();
  await expect(dialog.getByText(step.linkSent)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: s.email.submit })).toBeFocused();

  // The link the e-mail carries, opened on this device.
  const { link } = await postAsMember<{ link: string }>(page, "/v1/_test/step-up-link");
  await page.goto(sitePath(link));
  await expect(page).toHaveURL(/\/fr\/confirmer$/);
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: step.confirmSubmit }).click();
  await expect(page.getByRole("status")).toContainText(step.confirmed);
  await page.getByRole("link", { name: step.back }).click();
  await expect(page).toHaveURL(/\/fr\/compte\/parametres\/securite$/);

  // Now strong: the same request goes through without a dialog.
  await page.getByLabel(s.email.new).fill(newEmail);
  await page.getByRole("button", { name: s.email.submit }).click();
  await expect(page.getByRole("status")).toContainText(s.email.sent);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the link sent to the new address changes it, once", async ({ page }) => {
  await signIn(page, { completed: true });
  await page.goto("/fr");
  const newEmail = `e2e-confirm-${Date.now().toString(36)}@example.org`;
  const { link } = await postAsMember<{ link: string }>(page, "/v1/_test/email-change-link", {
    new_email: newEmail,
  });
  await page.goto(sitePath(link));
  await expect(page).toHaveURL(/\/fr\/compte\/email\/confirmer$/);
  await expectNoAxeViolations(page);
  await page.getByRole("button", { name: confirm.submit }).click();
  await expect(page.getByRole("status")).toContainText(confirm.done);
  expect(await meEmail(page)).toBe(newEmail);
  // Used once.
  await page.goto("about:blank");
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: confirm.submit }).click();
  await expect(page.getByRole("alert").filter({ hasText: confirm.invalid })).toBeVisible();
});

test("add passkey asks step-up, then rename and delete it", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
    },
  });
  await signIn(page, { completed: true, strong: false });
  await page.goto("/fr");
  // Passkeys opened to this member only (flag allow list), never to the tests running alongside.
  await postAsMember(page, "/v1/_test/flag-allow", { key: "auth.passkeys" });
  await page.goto("/fr/compte/parametres/securite");
  await expect(page.getByText(s.passkeys.none)).toBeVisible();
  await page.getByLabel(s.passkeys.addName).fill("Téléphone de test");
  await page.getByRole("button", { name: s.passkeys.add }).click();

  // No passkey yet: the strong proof goes by e-mail.
  const dialog = page.getByRole("dialog", { name: step.title });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: step.link }).click();
  await expect(dialog.getByText(step.linkSent)).toBeVisible();
  await page.keyboard.press("Escape");
  const { link } = await postAsMember<{ link: string }>(page, "/v1/_test/step-up-link");
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: step.confirmSubmit }).click();
  await page.getByRole("link", { name: step.back }).click();

  await page.getByLabel(s.passkeys.addName).fill("Téléphone de test");
  await page.getByRole("button", { name: s.passkeys.add }).click();
  await expect(page.getByRole("status")).toContainText(s.passkeys.added);
  await expect(page.getByText("Téléphone de test", { exact: true })).toBeVisible();
  await expectNoAxeViolations(page);

  await page
    .getByRole("button", { name: s.passkeys.renameLabel.replace("{name}", "Téléphone de test") })
    .click();
  await page.getByLabel(s.passkeys.name).fill("Ordinateur");
  await page.getByRole("button", { name: s.passkeys.save }).click();
  await expect(page.getByRole("status")).toContainText(s.passkeys.renamed);

  await page
    .getByRole("button", { name: s.passkeys.deleteLabel.replace("{name}", "Ordinateur") })
    .click();
  const confirmDelete = page.getByRole("dialog", {
    name: s.passkeys.deleteTitle.replace("{name}", "Ordinateur"),
  });
  await confirmDelete.getByRole("button", { name: s.passkeys.deleteConfirm }).click();
  await expect(page.getByRole("status")).toContainText(s.passkeys.deleted);
  await expect(page.getByText(s.passkeys.none)).toBeVisible();
});
