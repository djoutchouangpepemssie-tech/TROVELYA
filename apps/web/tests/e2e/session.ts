import type { Page } from "@playwright/test";

/** Sign the browser in as a new member through the test-only API route (ENV=test). */
export async function signIn(
  page: Page,
  options: { completed?: boolean } = {},
): Promise<{ userId: string; email: string }> {
  const response = await page.request.post("/api/v1/_test/session", {
    data: { completed: options.completed ?? false },
  });
  if (!response.ok()) throw new Error(`test session failed: ${String(response.status())}`);
  const body = (await response.json()) as { user_id: string; email: string };
  return { userId: body.user_id, email: body.email };
}
