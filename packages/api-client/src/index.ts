import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
/** Atalho para os schemas da API, ex.: Schemas["StudentDetail"]. */
export type Schemas = components["schemas"];

export interface ApiClientOptions {
  /** URL base do back, ex.: http://localhost:8000 */
  baseUrl: string;
  /** Devolve o token JWT atual (localStorage no web, SecureStore no mobile). */
  getToken?: () => string | null | undefined | Promise<string | null | undefined>;
  /** Chamado quando a API responde 401 (token expirado/inválido). */
  onUnauthorized?: () => void;
}

/**
 * Cliente HTTP tipado. Exemplo:
 *
 *   const api = createApiClient({ baseUrl, getToken });
 *   const { data, error } = await api.GET("/api/v1/students/{student_id}", {
 *     params: { path: { student_id: 1 } },
 *   });
 */
export function createApiClient({ baseUrl, getToken, onUnauthorized }: ApiClientOptions) {
  const client = createClient<paths>({ baseUrl });

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = await getToken?.();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
    async onResponse({ response }) {
      if (response.status === 401) onUnauthorized?.();
      return response;
    },
  };
  client.use(auth);

  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
