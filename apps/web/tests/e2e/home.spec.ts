import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import messages from "../../messages/fr.json" with { type: "json" };

test("redirects the root to /fr", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/fr$/);
});

test("home has lang=fr and text from the messages file", async ({ page }) => {
  await page.goto("/fr");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(messages.Home.brand);
  await expect(page.getByText(messages.Home.tagline)).toBeVisible();
  await expect(page).toHaveTitle(messages.Metadata.title);
});

test("security headers are present", async ({ request }) => {
  const response = await request.get("/fr");
  const headers = response.headers();
  const csp = headers["content-security-policy"] ?? "";
  const scriptSrc = csp.split(";").find((d) => d.trim().startsWith("script-src")) ?? "";
  expect(scriptSrc).toContain("'nonce-");
  expect(scriptSrc).not.toContain("'unsafe-inline'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers["strict-transport-security"]).toContain("max-age=63072000");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("the CSP nonce differs between two requests and is applied to scripts", async ({
  page,
  request,
}) => {
  const nonceOf = (csp: string) => /'nonce-([^']+)'/.exec(csp)?.[1];
  const first = nonceOf((await request.get("/fr")).headers()["content-security-policy"] ?? "");
  const second = nonceOf((await request.get("/fr")).headers()["content-security-policy"] ?? "");
  expect(first).toBeTruthy();
  expect(first).not.toBe(second);

  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) violations.push(message.text());
  });
  await page.goto("/fr");
  await page.waitForLoadState("networkidle");
  expect(violations).toEqual([]);
});

test("dark mode applies the dark tokens", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();
  await page.goto("/fr");
  const surface = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--trv-color-surface").trim(),
  );
  expect(surface.toLowerCase()).toBe("#0b0b0f");
  await context.close();
});

test("the site is installable (manifest and service worker)", async ({ page, request }) => {
  const manifest = (await (await request.get("/manifest.webmanifest")).json()) as {
    name: string;
    start_url: string;
    display: string;
    icons: { sizes: string; type: string }[];
  };
  expect(manifest.name).toBe(messages.Metadata.title);
  expect(manifest.start_url).toBe("/fr");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i) => i.sizes)).toEqual(
    expect.arrayContaining(["192x192", "512x512"]),
  );
  for (const icon of ["/icons/icon-192.png", "/icons/icon-512.png"]) {
    expect((await request.get(icon)).headers()["content-type"]).toBe("image/png");
  }

  await page.goto("/fr");
  await expect
    .poll(() => page.evaluate(async () => (await navigator.serviceWorker.ready).active?.state))
    .toBe("activated");
  await expect(page.locator('link[rel="manifest"]')).toHaveCount(1);
});

for (const width of [360, 1280]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`no accessibility violations at ${String(width)} px (${colorScheme})`, async ({
      browser,
    }) => {
      const context = await browser.newContext({ viewport: { width, height: 800 }, colorScheme });
      const page = await context.newPage();
      await page.goto("/fr");
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(serious).toEqual([]);
      await context.close();
    });
  }
}

for (const colorScheme of ["light", "dark"] as const) {
  test(`design system page has no accessibility violations (${colorScheme})`, async ({
    browser,
  }) => {
    const context = await browser.newContext({
      colorScheme,
      viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();
    await page.goto("/fr/design-system");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(messages.DesignSystem.title);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(serious).toEqual([]);
    await context.close();
  });
}

test("design system dialog traps focus and closes on Escape", async ({ page }) => {
  await page.goto("/fr/design-system");
  await page.getByRole("button", { name: messages.DesignSystem.dialogOpen }).click();
  const dialog = page.getByRole("dialog", { name: messages.DesignSystem.dialogTitle });
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 4; i += 1) await page.keyboard.press("Tab");
  expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
