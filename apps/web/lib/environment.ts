/** True on the public production deployment, where internal pages must not be served. */
export function isProduction(env: Record<string, string | undefined> = process.env): boolean {
  return env.VERCEL_ENV === "production" || env.APP_ENV === "production";
}
