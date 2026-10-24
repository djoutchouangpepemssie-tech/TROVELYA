import { relay } from "@/lib/relay";

// Every call reaches the API: nothing here is cached or prerendered.
export const dynamic = "force-dynamic";

async function handle(
  request: Request,
  context: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await context.params;
  return relay(request, path, {
    apiUrl: process.env.API_INTERNAL_URL ?? "",
    proxySecret: process.env.PROXY_SHARED_SECRET ?? "",
  });
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };
