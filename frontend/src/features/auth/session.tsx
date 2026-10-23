import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, api, onSessionExpired } from "@/lib/api";

export interface Session {
  username: string;
  full_name: string;
  email: string;
  roles: string[];
  /** Assente soltanto durante il rollout da backend legacy. */
  capabilities?: string[];
  is_admin: boolean;
  can_write: boolean;
}

interface SessionContextValue {
  session: Session | null;
  status: "loading" | "anonymous" | "authenticated";
  /** true quando la sessione è scaduta a lavoro aperto: si mostra il modale, non il login. */
  expired: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<SessionContextValue["status"]>("loading");
  const [expired, setExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get<Session>("/auth/session", { expectUnauthorized: true });
      setSession(data);
      setStatus("authenticated");
      setExpired(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setStatus("anonymous");
        setSession(null);
        return;
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // La sessione può scadere mentre l'utente lavora: non si fa logout, si chiede di
  // rientrare conservando lo stato dell'applicazione.
  useEffect(() => onSessionExpired(() => setExpired(true)), []);

  const signIn = useCallback(async (username: string, password: string) => {
    const data = await api.post<Session>(
      "/auth/login",
      { username, password },
      { expectUnauthorized: true },
    );
    setSession(data);
    setStatus("authenticated");
    setExpired(false);
  }, []);

  const signOut = useCallback(async () => {
    await api.post("/auth/logout");
    setSession(null);
    setStatus("anonymous");
    setExpired(false);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({ session, status, expired, signIn, signOut, refresh }),
    [session, status, expired, signIn, signOut, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook e provider stanno insieme per non duplicare il contesto
export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession va usato dentro SessionProvider.");
  }
  return context;
}
