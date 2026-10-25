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
