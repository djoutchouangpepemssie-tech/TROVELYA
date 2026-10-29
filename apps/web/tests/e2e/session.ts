import type { Page } from "@playwright/test";

/** Sign the browser in as a new member through the test-only API route (ENV=test). */
export async function signIn(
  page: Page,
  options: { completed?: boolean; strong?: boolean; email?: string } = {},
): Promise<{ userId: string; email: string }> {
  const response = await page.request.post("/api/v1/_test/session", {
    data: {
      completed: options.completed ?? false,
      strong: options.strong ?? true,
      ...(options.email ? { email: options.email } : {}),
    },
  });
  if (!response.ok()) throw new Error(`test session failed: ${String(response.status())}`);
  const body = (await response.json()) as { user_id: string; email: string };
  return { userId: body.user_id, email: body.email };
}

/**
 * POST from the page itself, as the browser would (session cookie and CSRF token): for the
 * test-only routes that act for the signed-in member. The page must be on the site.
 */
export async function postAsMember<T>(
  page: Page,
  path: `/v1/${string}`,
  body: unknown = {},
): Promise<T> {
  return page.evaluate(
    async ({ path, body }) => {
      await fetch("/api/v1/csrf");
      const token = /__Host-trv_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "";
      const response = await fetch(`/api${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-csrf-token": token },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`${path}: ${String(response.status)}`);
      return (response.status === 204 ? null : await response.json()) as T;
    },
    { path, body },
  );
}

/** A link e-mailed to the member, as a path on this site (`/fr/…#token=…`). */
export function sitePath(link: string): string {
  const url = new URL(link);
  return url.pathname + url.hash;
}

/**
 * Sign the browser in as a new staff superadmin, as the creation script and the enrolment page
 * do: a real WebAuthn ceremony on Chromium's virtual authenticator.
 */
export async function signInAsStaff(
  page: Page,
  text: { create: string; done: string },
): Promise<void> {
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
  if (!created.ok()) throw new Error(`staff enrolment failed: ${String(created.status())}`);
  const { link } = (await created.json()) as { link: string };
  await page.goto(sitePath(link));
  await page.getByRole("button", { name: text.create }).click();
  await page.getByRole("status").filter({ hasText: text.done }).waitFor();
}

/** A listing awaiting moderation (reason `weapons`), from the test-only catalog route. */
export async function listingInReview(page: Page): Promise<{ id: string; title: string }> {
  const response = await page.request.post("/api/v1/_test/listing-in-review", { data: {} });
  if (!response.ok()) throw new Error(`listing in review failed: ${String(response.status())}`);
  return (await response.json()) as { id: string; title: string };
}
