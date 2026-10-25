"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { authApi, type Me } from "@/lib/auth";

type Session = {
  /** undefined while loading, null when signed out. */
  me: Me | null | undefined;
  refresh: () => Promise<void>;
  /** Ends the session, then reloads `to`; false when the API did not confirm it. */
  signOut: (to: string) => Promise<boolean>;
};

const SessionContext = createContext<Session>({
  me: undefined,
  refresh: () => Promise.resolve(),
  signOut: () => Promise.resolve(false),
});

async function signOut(to: string): Promise<boolean> {
  if (!(await authApi.logout())) return false;
  // A full load: no page of the old session (nor its return address) survives on screen.
  window.location.assign(to);
  return true;
}

/** Who is signed in, read once per page from `/v1/me` and shared by the header and tabs. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const latest = useRef(0);
  const refresh = useCallback(async () => {
    // Only the latest request counts: the page-load answer (signed out) must not overwrite
    // the one asked right after signing in.
    const request = ++latest.current;
    const answer = await authApi.me();
    if (request !== latest.current) return;
    // A failed request (network, 5xx, 429) says nothing about the session: keep what we know,
    // so a passing error never sends a signed-in member to the sign-in page.
    setMe((known) => (answer === undefined ? known : answer));
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return (
    <SessionContext.Provider value={{ me, refresh, signOut }}>{children}</SessionContext.Provider>
  );
}

export function useSession(): Session {
  return useContext(SessionContext);
}
