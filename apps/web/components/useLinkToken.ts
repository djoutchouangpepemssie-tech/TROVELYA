"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The `#token=` of an e-mailed link: read once, then removed from the address bar and the
 * history at once (the fragment never reaches a server). `undefined` until read, `null` when
 * the link has none. Read once because the effect runs twice in development (strict mode).
 */
export function useLinkToken(): string | null | undefined {
  const read = useRef<string | null | undefined>(undefined);
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (read.current === undefined) {
      read.current = new URLSearchParams(window.location.hash.slice(1)).get("token");
      window.history.replaceState(null, "", window.location.pathname);
    }
    setToken(read.current);
  }, []);
  return token;
}
