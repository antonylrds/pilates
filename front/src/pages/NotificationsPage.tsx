import { Link } from "react-router-dom";

import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { useAsync } from "../lib/hooks";

const kindLabel: Record<string, string> = {
  plan_exhausted: "Plano esgotado",
  no_credits: "Sem aulas no plano",
};

export function NotificationsPage() {
  const list = useAsync(() => call(api.GET("/api/v1/notifications")), []);

  async function markRead(id: number) {
    await call(api.POST("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: id } } }));
    list.reload();
  }

  async function markAll() {
    await call(api.POST("/api/v1/notifications/read-all"));
    list.reload();
  }

  const unread = (list.data ?? []).filter((n) => !n.is_read).length;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Avisos</h1>
          <p className="muted">{unread} não lido(s)</p>
        </div>
        {unread > 0 && (
          <button className="btn" onClick={markAll}>
            Marcar todos como lidos
          </button>
        )}
      </header>

      {list.loading && !list.data && <Loading />}
      {list.error && <ErrorBox message={list.error} />}
      {list.data?.length === 0 && <Empty>Nenhum aviso por enquanto.</Empty>}

      <ul className="stack">
        {(list.data ?? []).map((n) => (
          <li key={n.id} className={`card notice ${n.is_read ? "is-read" : ""}`}>
            <div className="notice-main">
              <div className="notice-head">
                <Badge tone={n.kind === "plan_exhausted" ? "warning" : "danger"}>{kindLabel[n.kind] ?? n.kind}</Badge>
                <span className="muted small">{fmtDateTime(n.created_at)}</span>
              </div>
              <p>{n.message}</p>
              <Link to={`/alunos/${n.student.id}`} className="small">
                Ver ficha de {n.student.name} →
              </Link>
            </div>
            {!n.is_read && (
              <button className="btn btn-sm" onClick={() => markRead(n.id)}>
                Marcar como lido
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
