import { expect, test } from "@playwright/test";

import { signIn } from "./session";

test("the browser reaches the real API through the relay, with a session", async ({ page }) => {
  const { userId } = await signIn(page);
  const me = await page.request.get("/api/v1/me");
  expect(me.status()).toBe(200);
  const body = (await me.json()) as { id: string; profile_completed: boolean };
  expect(body.id).toBe(userId);
  expect(body.profile_completed).toBe(false);
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "__Host-trv_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.secure).toBe(true);
});
