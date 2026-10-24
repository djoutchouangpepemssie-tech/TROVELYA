import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };

const t = messages.StaffEnrolment;

test("staff enrolment: the link creates the passkey once, with a real WebAuthn ceremony", async ({
  page,
}) => {
  // Chromium's virtual authenticator: a platform passkey with user verification.
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

  const created = await page.request.post("/api/v1/_test/staff-enrolment", { data: {} });
  expect(created.ok()).toBe(true);
  const { link } = (await created.json()) as { link: string };
  const path = new URL(link).pathname + new URL(link).hash;

  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: t.title })).toBeVisible();
  // The token left the address bar.
  await expect(page).toHaveURL(/\/fr\/staff\/enrolement$/);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);

  await page.getByRole("button", { name: t.create }).click();
  await expect(page.getByRole("status")).toHaveText(t.done);

  // The staff session reaches the back office.
  const approvals = await page.evaluate(
    async () => (await fetch("/api/v1/staff/approvals")).status,
  );
  expect(approvals).toBe(200);

  // Second use of the same link (a fresh page load: a hash change alone does not reload).
  await page.goto("about:blank");
  await page.goto(path);
  await page.getByRole("button", { name: t.create }).click();
  await expect(page.getByRole("alert").filter({ hasText: t.errors.link_invalid })).toBeVisible();
});

test("staff enrolment without a token says the link is not valid", async ({ page }) => {
  await page.goto("/fr/staff/enrolement");
  await expect(page.getByRole("alert").filter({ hasText: t.errors.link_invalid })).toBeVisible();
  await expect(page.getByRole("button", { name: t.create })).toHaveCount(0);
});
