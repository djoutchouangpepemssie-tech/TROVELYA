import { headers } from "next/headers";

import { relay } from "./relay";

// Only what a read needs from the page request: who the visitor is (cookies), where they are
// (IP and country set by Vercel) and their language. Nothing else the browser sent.
const KEPT_HEADERS = [
  "accept-language",
  "cookie",
  "x-forwarded-for",
  "x-real-ip",
  "x-vercel-ip-country",
];

/**
 * GET from the API while rendering on the server, through the same relay as the browser:
 * the visitor's own cookies, IP and country go along (rate limits and the signed-in viewer
 * stay those of the visitor), plus the shared secret.
 */
export async function serverGet(path: readonly string[]): Promise<Response> {
  const incoming = await headers();
  const kept = new Headers();
  for (const name of KEPT_HEADERS) {
    const value = incoming.get(name);
    if (value !== null) kept.set(name, value);
  }
  const request = new Request("http://relay.internal/", { method: "GET", headers: kept });
  return relay(request, ["v1", ...path], {
    apiUrl: process.env.API_INTERNAL_URL ?? "",
    proxySecret: process.env.PROXY_SHARED_SECRET ?? "",
  });
}
