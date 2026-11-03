import type { Schemas } from "@pilates/api-client";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, call } from "../lib/api";
import { addDays, fmtDate, fmtHour, fmtShortDay, fmtWeekday, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { attendanceStatus, lessonStatus } from "../lib/labels";
import { Badge, ErrorBox, Loading } from "./ui";

type Props = { groupId: number; date: string; onClose: () => void; onChanged: () => void };
type Roster = Schemas["RosterEntry"];

const statusTone: Record<string, string> = {
  pending: "neutral",
  present: "success",
  absent: "danger",
  rescheduled: "warning",
};

export function LessonPanel({ groupId, date, onClose, onChanged }: Props) {
  const path = { class_group_id: groupId, lesson_date: date };
  const lesson = useAsync(
    () => call(api.GET("/api/v1/lessons/{class_group_id}/{lesson_date}", { params: { path } })),
    [groupId, date],
  );
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [moving, setMoving] = useState<Roster | null>(null);

  const isPastOrToday = date <= todayISO();
  const cancelled = lesson.data?.status === "cancelled";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      lesson.reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const mark = (studentId: number, status: "present" | "absent") =>
    run(() =>
      call(
        api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/attendance", {
          params: { path },
          body: { items: [{ student_id: studentId, status }] },
        }),
      ),
    );

  const undo = (studentId: number) =>
    run(() =>
      call(
        api.DELETE("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule/{student_id}", {
          params: { path: { ...path, student_id: studentId } },
        }),
      ),
    );

  const cancel = () => {
    const reason = window.prompt("Motivo do cancelamento (opcional):");
    if (reason === null) return;
    run(() =>
      call(
        api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/cancel", {
          params: { path },
          body: { reason: reason || null },
        }),
      ),
    );
  };

  const restore = () =>
    run(() => call(api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/restore", { params: { path } })));

  const data = lesson.data;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Detalhes da aula">
        <header className="drawer-header">
          <div>
            <div className="eyebrow">{fmtWeekday(date)}</div>
            <h2>{data?.class_group_name ?? "Aula"}</h2>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>

        {lesson.loading && !data && <Loading />}
        {lesson.error && <ErrorBox message={lesson.error} />}

        {data && (
          <div className="drawer-body">
            <dl className="facts">
              <div>
                <dt>Horário</dt>
                <dd>
                  {fmtHour(Number(data.starts_at.slice(11, 13)))} – {fmtHour(Number(data.ends_at.slice(11, 13)))}
                </dd>
              </div>
              <div>
                <dt>Sala</dt>
                <dd>{data.room.name}</dd>
              </div>
              <div>
                <dt>Professor</dt>
                <dd>{data.teacher.name}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <Badge tone={data.status}>{lessonStatus[data.status]}</Badge>
                </dd>
              </div>
              <div>
                <dt>Ocupação</dt>
                <dd>
                  {data.attendees_count} de {data.capacity}
                </dd>
              </div>
            </dl>

            {data.cancel_reason && <div className="alert alert-warning">Motivo: {data.cancel_reason}</div>}
            {error && <ErrorBox message={error} />}

            <h3 className="section-title">
              Chamada <span className="muted small">({data.students.length} aluno(s))</span>
            </h3>
            {data.students.length === 0 && <p className="muted">Nenhum aluno previsto nesta aula.</p>}
            <ul className="roster">
              {data.students.map((s) => (
                <li key={s.student.id} className="roster-item">
                  <div className="roster-main">
                    <Link to={`/alunos/${s.student.id}`} className="roster-name">
                      {s.student.name}
                    </Link>
                    <div className="roster-meta">
                      <Badge tone={statusTone[s.status]}>{attendanceStatus[s.status]}</Badge>
                      {s.is_makeup && s.makeup_from && (
                        <span className="muted small">Reposição de {fmtDate(s.makeup_from.date)}</span>
                      )}
                      {s.rescheduled_to && (
                        <span className="muted small">
                          → {fmtDate(s.rescheduled_to.date)} {fmtHour(s.rescheduled_to.start_hour)}
                        </span>
                      )}
                      <span className={`small ${s.credits_remaining === 0 ? "text-danger" : "muted"}`}>
                        {s.credits_remaining} aula(s) restante(s)
                      </span>
                    </div>
                  </div>
                  {!cancelled && (
                    <div className="roster-actions">
                      {s.status === "rescheduled" ? (
                        <button className="btn btn-sm" disabled={busy} onClick={() => undo(s.student.id)}>
                          Desfazer
                        </button>
                      ) : isPastOrToday ? (
                        <>
                          <button
                            className={`btn btn-sm ${s.status === "present" ? "btn-success" : ""}`}
                            disabled={busy}
                            onClick={() => mark(s.student.id, "present")}
                          >
                            Presente
                          </button>
                          <button
                            className={`btn btn-sm ${s.status === "absent" ? "btn-danger" : ""}`}
                            disabled={busy}
                            onClick={() => mark(s.student.id, "absent")}
                          >
                            Falta
                          </button>
                        </>
                      ) : null}
                      {s.status === "pending" && (
                        <button className="btn btn-sm" disabled={busy} onClick={() => setMoving(s)}>
                          Reagendar
                        </button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>

            {moving && (
              <ReschedulePicker
                student={moving}
                fromGroupId={groupId}
                fromDate={date}
                onCancel={() => setMoving(null)}
                onPick={(target) =>
                  run(async () => {
                    await call(
                      api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule", {
                        params: { path },
                        body: {
                          student_id: moving.student.id,
                          target_class_group_id: target.class_group_id,
                          target_date: target.date,
                        },
                      }),
                    );
                    setMoving(null);
                  })
                }
              />
            )}

            <footer className="drawer-footer">
              {cancelled ? (
                <button className="btn" disabled={busy} onClick={restore}>
                  Desfazer cancelamento
                </button>
              ) : (
                <button className="btn btn-danger-outline" disabled={busy} onClick={cancel}>
                  Cancelar aula
                </button>
              )}
            </footer>
          </div>
        )}
      </aside>
    </div>
  );
}

function ReschedulePicker({
  student,
  fromGroupId,
  fromDate,
  onPick,
  onCancel,
}: {
  student: Roster;
  fromGroupId: number;
  fromDate: string;
  onPick: (entry: Schemas["CalendarEntry"]) => void;
  onCancel: () => void;
}) {
  const today = todayISO();
  const start = fromDate > today ? fromDate : today;
  const end = toISO(addDays(parseISO(start), 13));
  const nowHour = new Date().getHours();
  const isUpcoming = (e: Schemas["CalendarEntry"]) =>
    e.date > today || (e.date === today && Number(e.starts_at.slice(11, 13)) > nowHour);
  const options = useAsync(
    () => call(api.GET("/api/v1/calendar", { params: { query: { date_from: start, date_to: end } } })),
    [start],
  );
  const available = (options.data ?? []).filter(
    (e) =>
      e.status !== "cancelled" &&
      e.available_spots > 0 &&
      !(e.class_group_id === fromGroupId && e.date === fromDate) &&
      isUpcoming(e),
  );

  return (
    <div className="picker">
      <div className="picker-header">
        <strong>Reagendar {student.student.name}</strong>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>
          Fechar
        </button>
      </div>
      <p className="muted small">Aulas com vaga nos próximos 14 dias. O horário padrão do aluno não muda.</p>
      {options.loading && <Loading />}
      <div className="picker-list">
        {available.map((e) => (
          <button key={`${e.class_group_id}-${e.date}`} className="picker-option" onClick={() => onPick(e)}>
            <span>
              {fmtShortDay(e.date)} · {fmtHour(Number(e.starts_at.slice(11, 13)))}
            </span>
            <span className="muted small">
              {e.room.name} · {e.teacher.name.split(" ")[0]} · {e.available_spots} vaga(s)
            </span>
          </button>
        ))}
        {!options.loading && available.length === 0 && <p className="muted">Nenhuma aula com vaga.</p>}
      </div>
    </div>
  );
}
