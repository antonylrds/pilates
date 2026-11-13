import type { Schemas } from "@pilates/api-client";
import { createContext, type ReactNode, useContext, useState } from "react";

import {
  api,
  call,
  clearPlatform,
  clearSession,
  loadPlatform,
  loadSession,
  type PlatformSession,
  platformApi,
  savePlatform,
  saveSession,
  type Session,
  storeSession,
} from "./api";

type SessionContextValue = {
  session: Session | null;
  isAdmin: boolean;
  /** Usuário da plataforma logado (pode escolher um estúdio e um usuário para "ver como"). */
  platform: PlatformSession | null;
  login: (studio: string, email: string, password: string) => Promise<void>;
  loginPlatform: (email: string, password: string) => Promise<void>;
  /** "Ver como": passa a ver o estúdio como o usuário `userId` (admin ou professor), com a conta da plataforma. */
  viewAs: (studioId: number, userId: number) => Promise<void>;
  /** Sai do estúdio (do "ver como", volta à plataforma). */
  logout: () => void;
  /** Sai também da conta da plataforma. */
  platformLogout: () => void;
  updateStudio: (studio: Schemas["StudioRead"]) => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [platform, setPlatform] = useState<PlatformSession | null>(() => loadPlatform());

  async function login(studio: string, email: string, password: string) {
    const token = await call(api.POST("/api/v1/auth/login", { body: { studio, email, password } }));
    setSession(saveSession(token));
  }

  async function loginPlatform(email: string, password: string) {
    const token = await call(platformApi.POST("/api/v1/platform/auth/login", { body: { email, password } }));
    setPlatform(savePlatform({ token: token.access_token, email }));
  }

  async function viewAs(studioId: number, userId: number) {
    const token = await call(
      platformApi.POST("/api/v1/platform/studios/{studio_id}/impersonate", {
        params: { path: { studio_id: studioId } },
        body: { user_id: userId },
      }),
    );
    setSession(saveSession(token));
  }

  function logout() {
    clearSession();
    setSession(null);
  }

  function platformLogout() {
    clearPlatform();
    clearSession();
    setPlatform(null);
    setSession(null);
  }

  function updateStudio(studio: Schemas["StudioRead"]) {
    setSession((current) => (current ? storeSession({ ...current, studio }) : current));
  }

  const isAdmin = session?.user.role === "admin";

  return (
    <SessionContext.Provider
      value={{ session, isAdmin, platform, login, loginPlatform, viewAs, logout, platformLogout, updateStudio }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession fora do SessionProvider");
  return ctx;
}
