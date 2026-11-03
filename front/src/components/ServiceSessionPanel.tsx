import { useState } from "react";
import { Link } from "react-router-dom";

import { api, call } from "../lib/api";
import { fmtDateTime, fmtHour, fmtWeekday, money } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Badge, ErrorBox, Loading } from "./ui";

export const sessionStatus: Record<string, [string, string]> = {
  scheduled: ["Agendada", "info"],
  done: ["Presente", "success"],
  missed: ["Falta", "danger"],
  cancelled: ["Cancelada", "neutral"],
};

type Props = { sessionId: number; onClose: () => void; onChanged: () => void };

/** Detalhe de uma sessão de serviço avulso (agenda e ficha do aluno). */
export function ServiceSessionPanel({ sessionId, onClose, onChanged }: Props) {
  const { isAdmin } = useSession();
  const detail = useAsync(
    () => call(api.GET("/api/v1/service-sessions/{session_id}", { params: { path: { session_id: sessionId } } })),
    [sessionId],
  );
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      detail.reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const s = detail.data;
  const setStatus = (status: "scheduled" | "cancelled") =>
    s &&
    run(() =>
      call(
        api.PATCH("/api/v1/students/{student_id}/services/{contract_id}/sessions/{session_id}", {
          params: { path: { student_id: s.student.id, contract_id: s.contract_id, session_id: s.id } },
          body: { status },
        }),
      ),
    );

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Sessão de serviço">
        <header className="drawer-header">
          <div>
            <div className="eyebrow">{s ? fmtWeekday(s.date) : "Serviço avulso"}</div>
            <h2>{s ? `${s.service_name} · ${s.student.name}` : "Sessão"}</h2>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>
        {detail.loading && !s && <Loading />}
        {detail.error && <ErrorBox message={detail.error} />}
        {s && (
          <div className="drawer-body">
            <dl className="facts">
              <div>
                <dt>Horário</dt>
                <dd>{s.start_hour != null ? `${fmtHour(s.start_hour)} – ${fmtHour(s.start_hour + 1)}` : "—"}</dd>
              </div>
              <div>
                <dt>Sala</dt>
                <dd>{s.room?.name ?? "—"}</dd>
              </div>
              <div>
                <dt>Profissional</dt>
                <dd>{s.teacher?.name ?? "—"}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <Badge tone={sessionStatus[s.status][1]}>{sessionStatus[s.status][0]}</Badge>
                </dd>
              </div>
              <div>
                <dt>Valor da sessão</dt>
                <dd>{money(s.price)}</dd>
              </div>
            </dl>
            <p>
              <Link to={`/alunos/${s.student.id}`}>Ver ficha de {s.student.name} →</Link>
            </p>
            {s.notes && <div className="alert alert-info">📝 {s.notes}</div>}
            {s.completed_at && (
              <div className="alert alert-info">
                Finalizada em {fmtDateTime(s.completed_at)}
                {s.teacher_pay != null && (
                  <>
                    {" "}
                    · profissional recebe {money(s.teacher_pay)} ({Number(s.share_percent)}%)
                  </>
                )}
                {s.justification && <> · “{s.justification}”</>}
              </div>
            )}
            {s.can_complete && (
              <Link to={`/finalizar/servico/${s.id}`} className="btn btn-primary btn-block">
                Finalizar sessão
              </Link>
            )}
            {error && <ErrorBox message={error} />}
            {isAdmin && (
              <footer className="drawer-footer">
                {s.completed_at ? (
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() =>
                      window.confirm("Reabrir a sessão? O valor do profissional sai do relatório.") &&
                      run(() =>
                        call(api.POST("/api/v1/service-sessions/{session_id}/reopen", { params: { path: { session_id: s.id } } })),
                      )
                    }
                  >
                    Reabrir sessão
                  </button>
                ) : s.status === "cancelled" ? (
                  <button className="btn" disabled={busy} onClick={() => setStatus("scheduled")}>
                    Reativar sessão
                  </button>
                ) : (
                  <button className="btn btn-danger-outline" disabled={busy} onClick={() => setStatus("cancelled")}>
                    Cancelar sessão
                  </button>
                )}
              </footer>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
