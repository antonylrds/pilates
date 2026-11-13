import { useState } from "react";

import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { call, platformApi } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { roleLabel } from "../lib/labels";
import { useSession } from "../lib/session";

/** Visão da plataforma: lista os estúdios e deixa ver o sistema como o admin ou um professor de cada um. */
export function PlatformPage() {
  const { platform, platformLogout } = useSession();
  const studios = useAsync(() => call(platformApi.GET("/api/v1/platform/studios")), []);
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <div className="platform">
      <header className="platform-head">
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <div className="brand-name">Plataforma</div>
            <div className="brand-sub">{platform?.email}</div>
          </div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={platformLogout}>
          Sair
        </button>
      </header>

      <div className="card">
        <h3 className="card-title">Estúdios</h3>
        <p className="muted small">
          Escolha um estúdio e um usuário para ver o sistema como ele (administrador ou professor). Suas ações ficam
          registradas com o seu nome, e a troca de senhas fica bloqueada nesse modo.
        </p>
        {studios.loading && !studios.data && <Loading />}
        {studios.error && <ErrorBox message={studios.error} />}
        {studios.data?.length === 0 && <Empty>Nenhum estúdio cadastrado.</Empty>}
        {studios.data && studios.data.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Estúdio</th>
                <th>Identificador</th>
                <th>Situação</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {studios.data.map((studio) => (
                <StudioRows
                  key={studio.id}
                  studio={studio}
                  open={openId === studio.id}
                  onToggle={() => setOpenId(openId === studio.id ? null : studio.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

type Studio = { id: number; name: string; slug: string; is_active: boolean };

function StudioRows({ studio, open, onToggle }: { studio: Studio; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr>
        <td>{studio.name}</td>
        <td>
          <code>{studio.slug}</code>
        </td>
        <td>
          <Badge tone={studio.is_active ? "success" : "neutral"}>{studio.is_active ? "Ativo" : "Inativo"}</Badge>
        </td>
        <td className="num">
          <button className="btn btn-sm" onClick={onToggle} disabled={!studio.is_active}>
            {open ? "Fechar" : "Ver como…"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={4}>
            <StudioUsers studio={studio} />
          </td>
        </tr>
      )}
    </>
  );
}

function StudioUsers({ studio }: { studio: Studio }) {
  const { viewAs } = useSession();
  const users = useAsync(
    () =>
      call(
        platformApi.GET("/api/v1/platform/studios/{studio_id}/users", { params: { path: { studio_id: studio.id } } }),
      ),
    [studio.id],
  );
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string>();

  async function enter(userId: number) {
    setBusyId(userId);
    setError(undefined);
    try {
      await viewAs(studio.id, userId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusyId(null);
    }
  }

  return (
    <div className="platform-users">
      {users.loading && !users.data && <Loading />}
      {users.error && <ErrorBox message={users.error} />}
      {error && <ErrorBox message={error} />}
      {users.data && (
        <ul className="platform-user-list">
          {users.data.map((user) => (
            <li key={user.id}>
              <div>
                <strong>{user.name}</strong>{" "}
                <Badge tone={user.role === "admin" ? "success" : "neutral"}>{roleLabel(user.role)}</Badge>{" "}
                {!user.is_active && <Badge tone="danger">Inativo</Badge>}
                <div className="muted small">{user.email}</div>
              </div>
              <button
                className="btn btn-primary btn-sm"
                disabled={!user.is_active || busyId !== null}
                onClick={() => enter(user.id)}
              >
                {busyId === user.id ? "Entrando…" : "Ver como"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
