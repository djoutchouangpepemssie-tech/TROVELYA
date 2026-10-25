/**
 * True when a path has a broken percent escape ("%E0", "%zz"): Next.js would throw while
 * decoding the route parameters and answer 500, so the proxy answers 400 first.
 */
export function hasMalformedEscape(pathname: string): boolean {
  try {
    decodeURIComponent(pathname);
    return false;
  } catch {
    return true;
  }
}
