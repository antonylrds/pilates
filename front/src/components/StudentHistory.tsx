import { useState } from "react";

import { api, call } from "../lib/api";
import { fmtDate, fmtDateTime, fmtHour } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { attendanceStatus, attendanceTone } from "../lib/labels";
import { Badge, ErrorBox, Loading } from "./ui";

type Common = { studentId: number; version: number };

const scheduleStatus: Record<string, [string, string]> = {
  current: ["Atual", "success"],
  future: ["A partir de", "info"],
  ended: ["Encerrado", "neutral"],
};

/** Horários padrão anteriores e futuros (o atual aparece no card "Turmas padrão"). */
export function ScheduleHistory({ studentId, version }: Common) {
  const history = useAsync(
    () =>
      call(api.GET("/api/v1/students/{student_id}/schedule/history", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );
  const items = (history.data ?? []).filter((h) => h.status !== "current" || h.end_date !== null);
  if (history.loading && !history.data) return <Loading />;
  if (history.error) return <ErrorBox message={history.error} />;
  if (items.length === 0) return <p className="muted small">Sem mudanças de horário.</p>;

  return (
    <ul className="schedule-history">
      {items.map((h) => {
        const [label, tone] = scheduleStatus[h.status];
        return (
          <li key={h.enrollment_id}>
            <span>
              <strong>{h.weekday_name}</strong> {fmtHour(h.start_hour)} · {h.room} · {h.teacher}
            </span>
            <span className="muted small">
              {fmtDate(h.start_date)} → {h.end_date ? fmtDate(h.end_date) : "atual"}
            </span>
            <Badge tone={tone}>{label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

/** Aulas do aluno (presenças, faltas, reagendamentos), independentes do horário padrão atual. */
export function AttendanceHistory({ studentId, version, onOpenLesson }: Common & {
  onOpenLesson: (groupId: number, date: string) => void;
}) {
  const [limit, setLimit] = useState(10);
  const history = useAsync(
    () =>
      call(
        api.GET("/api/v1/students/{student_id}/attendances", {
          params: { path: { student_id: studentId }, query: { limit: limit + 1 } },
        }),
      ),
    [studentId, version, limit],
  );
  const rows = (history.data ?? []).slice(0, limit);
  const hasMore = (history.data?.length ?? 0) > limit;

  return (
    <div className="card">
      <h3 className="card-title">
        Histórico de aulas <span className="muted small">(mantido mesmo se o horário padrão mudar)</span>
      </h3>
      {history.loading && !history.data && <Loading />}
      {history.error && <ErrorBox message={history.error} />}
      {history.data?.length === 0 && <p className="muted">Nenhuma aula registrada.</p>}
      {rows.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Turma</th>
              <th>Situação</th>
              <th>Justificativa</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={`${a.lesson.class_group_id}-${a.lesson.date}`}>
                <td>
                  <button className="link-button" onClick={() => onOpenLesson(a.lesson.class_group_id, a.lesson.date)}>
                    {fmtDate(a.lesson.date)} {fmtHour(a.lesson.start_hour)}
                  </button>
                </td>
                <td className="small">
                  {a.lesson.class_group_name}
                  {a.is_makeup && <span className="muted"> · reposição</span>}
                </td>
                <td>
                  <Badge tone={attendanceTone[a.status]}>{attendanceStatus[a.status]}</Badge>
                  {!a.lesson_completed && a.status !== "rescheduled" && (
                    <span className="muted small"> · aguardando</span>
                  )}
                </td>
                <td className="small muted">{a.justification ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {hasMore && (
        <button className="btn btn-sm btn-ghost" onClick={() => setLimit(limit + 20)}>
          Ver mais
        </button>
      )}
    </div>
  );
}

const actionIcon: Record<string, string> = {
  student_created: "＋",
  student_updated: "✎",
  schedule_changed: "▦",
  plan_added: "★",
  plan_cancelled: "✕",
  payment_updated: "$",
  student_deactivated: "⏸",
  student_reactivated: "▶",
  service_contracted: "✚",
  service_updated: "✎",
  service_cancelled: "✕",
};

/** Registro de alterações: o que mudou, quem fez e quando. */
export function ChangeLog({ studentId, version }: Common) {
  const log = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}/history", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );
  return (
    <div className="card">
      <h3 className="card-title">Histórico de alterações</h3>
      {log.loading && !log.data && <Loading />}
      {log.error && <ErrorBox message={log.error} />}
      {log.data?.length === 0 && <p className="muted">Nenhuma alteração registrada.</p>}
      <ol className="changelog">
        {(log.data ?? []).map((entry) => (
          <li key={entry.id}>
            <span className="changelog-icon" aria-hidden>
              {actionIcon[entry.action] ?? "•"}
            </span>
            <div>
              <p>{entry.description}</p>
              <p className="muted small">
                {entry.user_name} · {fmtDateTime(entry.created_at)}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
