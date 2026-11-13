import { useState } from "react";

import { call, platformApi } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { roleLabel } from "../lib/labels";
import { useSession } from "../lib/session";

/** Faixa do modo "ver como" (usuário da plataforma): mostra quem está sendo visto e permite trocar de visão. */
export function ViewAsBar() {
  const { session } = useSession();
  return session?.impersonatedBy ? <ActiveViewAsBar /> : null;
}

function ActiveViewAsBar() {
  const { session, viewAs, logout } = useSession();
  const studioId = session?.studio.id ?? 0;
  const users = useAsync(
    () =>
      call(
        platformApi.GET("/api/v1/platform/studios/{studio_id}/users", {
          params: { path: { studio_id: studioId } },
        }),
      ),
    [studioId],
  );
  const [error, setError] = useState<string>();

  async function switchTo(userId: number) {
    setError(undefined);
    try {
      await viewAs(studioId, userId);
      // Recarrega: páginas abertas (ex.: Caixa) podem não existir na nova visão.
      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!session) return null;

  return (
    <div className="viewas-bar" role="status">
      <span>
        <strong>Modo plataforma</strong> · vendo <strong>{session.studio.name}</strong> como{" "}
        <strong>{session.user.name}</strong> ({roleLabel(session.user.role)})
      </span>
      <label className="viewas-switch">
        <span>Trocar visão:</span>
        <select value={session.user.id} onChange={(e) => switchTo(Number(e.target.value))}>
          {(users.data ?? [])
            .filter((u) => u.is_active || u.id === session.user.id)
            .map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} — {roleLabel(u.role)}
              </option>
            ))}
        </select>
      </label>
      {error && <span className="viewas-error">{error}</span>}
      <button className="btn btn-sm" onClick={logout}>
        Voltar à plataforma
      </button>
    </div>
  );
}
