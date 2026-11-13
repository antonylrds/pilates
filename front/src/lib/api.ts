import { createApiClient, type Schemas } from "@pilates/api-client";

const TOKEN_KEY = "pilates.token";
const SESSION_KEY = "pilates.session";
const PLATFORM_KEY = "pilates.platform";

export type Session = {
  user: Schemas["UserRead"];
  studio: Schemas["StudioRead"];
  /** Nome do usuário da plataforma, quando a sessão é um "ver como". */
  impersonatedBy?: string | null;
};

/** Sessão do usuário da plataforma (escolhe o estúdio e o usuário a ver). */
export type PlatformSession = { token: string; email: string };

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return read(TOKEN_KEY);
}

export function loadSession(): Session | null {
  const raw = read(SESSION_KEY);
  if (!raw || !getToken()) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function saveSession(token: Schemas["Token"]): Session {
  try {
    localStorage.setItem(TOKEN_KEY, token.access_token);
  } catch {
    /* modo privado: a sessão vale só nesta aba */
  }
  return storeSession({ user: token.user, studio: token.studio, impersonatedBy: token.impersonated_by ?? null });
}

export function storeSession(session: Session): Session {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    /* ignore */
  }
  return session;
}

export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function loadPlatform(): PlatformSession | null {
  const raw = read(PLATFORM_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PlatformSession;
  } catch {
    return null;
  }
}

export function savePlatform(platform: PlatformSession): PlatformSession {
  try {
    localStorage.setItem(PLATFORM_KEY, JSON.stringify(platform));
  } catch {
    /* modo privado: vale só nesta aba */
  }
  return platform;
}

export function clearPlatform(): void {
  try {
    localStorage.removeItem(PLATFORM_KEY);
  } catch {
    /* ignore */
  }
}

export const api = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL || window.location.origin,
  getToken,
  onUnauthorized: () => {
    if (getToken()) {
      clearSession();
      window.location.assign("/login");
    }
  },
});

/** fetch autenticado (upload/download de arquivos, que o cliente tipado não cobre). Usa o mesmo token e URL base. */
export function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const base = import.meta.env.VITE_API_URL || window.location.origin;
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${base}${path}`, { ...init, headers }).then((response) => {
    if (response.status === 401 && token) {
      clearSession();
      window.location.assign("/login");
    }
    return response;
  });
}

export function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  }
  return "Erro inesperado. Verifique se a API está rodando.";
}

/** Desembrulha a resposta do openapi-fetch: devolve `data` ou lança um Error com a mensagem da API. */
export async function call<R extends { data?: unknown; error?: unknown }>(
  request: Promise<R>,
): Promise<NonNullable<R["data"]>> {
  const { data, error } = await request;
  if (error !== undefined) throw new Error(errorMessage(error));
  return data as NonNullable<R["data"]>;
}

/** Cliente com o token da plataforma (rotas /platform). Separado do `api`, que usa o token do estúdio. */
export const platformApi = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL || window.location.origin,
  getToken: () => loadPlatform()?.token,
  onUnauthorized: () => {
    if (loadPlatform()) {
      clearPlatform();
      clearSession();
      window.location.assign("/login");
    }
  },
});
