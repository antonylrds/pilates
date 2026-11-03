import type { Schemas } from "@pilates/api-client";
import { createContext, type ReactNode, useContext, useState } from "react";

import { api, call, clearSession, loadSession, saveSession, type Session, storeSession } from "./api";

type SessionContextValue = {
  session: Session | null;
  isAdmin: boolean;
  login: (studio: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  updateStudio: (studio: Schemas["StudioRead"]) => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => loadSession());

  async function login(studio: string, email: string, password: string) {
    const token = await call(api.POST("/api/v1/auth/login", { body: { studio, email, password } }));
    setSession(saveSession(token));
  }

  function logout() {
    clearSession();
    setSession(null);
  }

  function updateStudio(studio: Schemas["StudioRead"]) {
    setSession((current) => (current ? storeSession({ ...current, studio }) : current));
  }

  const isAdmin = session?.user.role === "admin";

  return (
    <SessionContext.Provider value={{ session, isAdmin, login, logout, updateStudio }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession fora do SessionProvider");
  return ctx;
}
