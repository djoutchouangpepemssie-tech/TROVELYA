import { headers } from "next/headers";

import { relay } from "./relay";

/**
 * GET from the API while rendering on the server, through the same relay as the browser:
 * the visitor's own cookies, IP and country go along (rate limits and the signed-in viewer
 * stay those of the visitor), plus the shared secret.
 */
export async function serverGet(path: readonly string[]): Promise<Response> {
  const incoming = await headers();
  const request = new Request("http://relay.internal/", { method: "GET", headers: incoming });
  return relay(request, ["v1", ...path], {
    apiUrl: process.env.API_INTERNAL_URL ?? "",
    proxySecret: process.env.PROXY_SHARED_SECRET ?? "",
  });
}
