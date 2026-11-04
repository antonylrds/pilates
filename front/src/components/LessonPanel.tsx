import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { api, call } from "../lib/api";
import { fmtDate, fmtDateTime, fmtHour, fmtWeekday } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { attendanceStatus, attendanceTone, lessonStatus } from "../lib/labels";
import { useSession } from "../lib/session";
import { ConfirmPanel } from "./ConfirmPanel";
import { LessonAddStudent } from "./LessonAddStudent";
import { ReschedulePicker } from "./ReschedulePicker";
import { Badge, ErrorBox, Loading } from "./ui";

type Props = { groupId: number; date: string; onClose: () => void; onChanged: () => void };
type Roster = Schemas["RosterEntry"];

export function LessonPanel({ groupId, date, onClose, onChanged }: Props) {
  const { isAdmin } = useSession();
  const path = { class_group_id: groupId, lesson_date: date };
  const lesson = useAsync(
    () => call(api.GET("/api/v1/lessons/{class_group_id}/{lesson_date}", { params: { path } })),
    [groupId, date],
  );
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [moving, setMoving] = useState<Roster | null>(null);
  const [justification, setJustification] = useState("");
  const [teacherEdit, setTeacherEdit] = useState<number | null>(null);
  const teachers = useAsync(
    () => (teacherEdit === null ? Promise.resolve([]) : call(api.GET("/api/v1/teachers"))),
    [teacherEdit === null],
  );

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      lesson.reload();
      onChanged();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const undo = (studentId: number) =>
    run(() =>
      call(
        api.DELETE("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule/{student_id}", {
          params: { path: { ...path, student_id: studentId } },
        }),
      ),
    );

  const removeDropIn = (studentId: number) =>
    run(() =>
      call(
        api.DELETE("/api/v1/lessons/{class_group_id}/{lesson_date}/drop-in/{student_id}", {
          params: { path: { ...path, student_id: studentId } },
        }),
      ),
    );

  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const cancel = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(() =>
      call(
        api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/cancel", {
          params: { path },
          body: { reason: cancelReason.trim() || null },
        }),
      ),
    );
    if (ok) {
      setCancelling(false);
      setCancelReason("");
    }
  };

  const changeTeacher = async () => {
    if (teacherEdit === null) return;
    const ok = await run(() =>
      call(
        api.PATCH("/api/v1/lessons/{class_group_id}/{lesson_date}", {
          params: { path },
          body: { teacher_id: teacherEdit },
        }),
      ),
    );
    if (ok) setTeacherEdit(null);
  };

  const restore = () =>
    run(() => call(api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/restore", { params: { path } })));

  const [reopening, setReopening] = useState(false);
  const reopen = async () => {
    const ok = await run(() => call(api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/reopen", { params: { path } })));
    if (ok) setReopening(false);
  };

  const data = lesson.data;
  const completed = data?.status === "completed";
  const cancelled = data?.status === "cancelled";
  const open = !completed && !cancelled;
  // Reagendamento antecipado: só antes da aula começar (depois disso, é feito na finalização).
  const canReschedule = open && data && !data.can_complete;
  // Incluir alunos: só antes da aula começar.
  const notStarted = !!data && new Date(data.starts_at) > new Date();
  const substitute = !!data && data.teacher.id !== data.default_teacher.id;

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
                <dd>
                  {teacherEdit === null ? (
                    <span className="teacher-fact">
                      {data.teacher.name}
                      {substitute && <span className="muted small"> (substituto · titular: {data.default_teacher.name})</span>}
                      {open && isAdmin && (
                        <button className="btn btn-sm btn-ghost" onClick={() => setTeacherEdit(data.teacher.id)}>
                          Alterar
                        </button>
                      )}
                    </span>
                  ) : (
                    <span className="teacher-edit">
                      <select
                        value={teacherEdit}
                        onChange={(e) => setTeacherEdit(Number(e.target.value))}
                        aria-label="Professor desta aula"
                      >
                        {(teachers.data ?? [data.teacher]).map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                            {t.id === data.default_teacher.id ? " (titular)" : ""}
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn btn-sm btn-primary"
                        disabled={busy || teacherEdit === data.teacher.id}
                        onClick={changeTeacher}
                      >
                        Salvar
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => setTeacherEdit(null)}>
                        Cancelar
                      </button>
                      <small className="muted">Vale só para esta data; a turma continua com o titular.</small>
                    </span>
                  )}
                </dd>
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
            {completed && data.completed_at && (
              <div className="alert alert-info">
                Concluída em {fmtDateTime(data.completed_at)}
                {data.completed_by && <> por {data.completed_by}</>}.
              </div>
            )}
            {data.can_complete && (
              <Link to={`/finalizar/${groupId}/${date}`} className="btn btn-primary btn-block">
                Finalizar aula
              </Link>
            )}
            {error && <ErrorBox message={error} />}

            <h3 className="section-title">
              Alunos <span className="muted small">({data.students.length})</span>
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
                      <Badge tone={attendanceTone[s.status]}>{attendanceStatus[s.status]}</Badge>
                      {s.is_drop_in && <Badge tone="info">Avulsa</Badge>}
                      {s.is_makeup && s.makeup_from && (
                        <span className="muted small">Reposição de {fmtDate(s.makeup_from.date)}</span>
                      )}
                      {s.reschedule_count > 0 && (
                        <span
                          className={`resched-count ${s.reschedule_count >= 2 ? "is-high" : ""}`}
                          title={s.original_lesson ? `Aula original: ${fmtDate(s.original_lesson.date)} ${fmtHour(s.original_lesson.start_hour)}` : undefined}
                        >
                          ↻ {s.reschedule_count}x
                          {s.original_lesson && s.reschedule_count > 1 && <> · original {fmtDate(s.original_lesson.date)}</>}
                        </span>
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
                    {s.justification && <p className="justification">“{s.justification}”</p>}
                  </div>
                  {open && (
                    <div className="roster-actions">
                      {s.status === "rescheduled" ? (
                        <button className="btn btn-sm" disabled={busy} onClick={() => undo(s.student.id)}>
                          Desfazer
                        </button>
                      ) : (
                        canReschedule &&
                        s.status === "pending" && (
                          <>
                          {s.is_drop_in && (
                            <button className="btn btn-sm btn-ghost" disabled={busy} onClick={() => removeDropIn(s.student.id)}>
                              Remover
                            </button>
                          )}
                          <button
                            className="btn btn-sm"
                            disabled={busy}
                            onClick={() => {
                              setMoving(s);
                              setJustification("");
                            }}
                          >
                            Reagendar
                          </button>
                          </>
                        )
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>

            {open && notStarted && (
              <LessonAddStudent key={`${groupId}|${date}`} groupId={groupId} date={date} lesson={data} busy={busy} run={run} />
            )}

            {moving && (
              <div className="picker">
                <div className="picker-header">
                  <strong>Reagendar {moving.student.name}</strong>
                  <button className="btn btn-ghost btn-sm" onClick={() => setMoving(null)}>
                    Fechar
                  </button>
                </div>
                <label className="field">
                  <span>Justificativa (opcional)</span>
                  <input
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    placeholder="Ex.: viagem, consulta médica…"
                    maxLength={500}
                  />
                </label>
                <p className="muted small">Escolha a aula de reposição. O horário padrão do aluno não muda.</p>
                <ReschedulePicker
                  fromGroupId={groupId}
                  fromDate={date}
                  onPick={async (target) => {
                    const ok = await run(() =>
                      call(
                        api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule", {
                          params: { path },
                          body: {
                            student_id: moving.student.id,
                            target_class_group_id: target.class_group_id,
                            target_date: target.date,
                            justification: justification || null,
                          },
                        }),
                      ),
                    );
                    if (ok) setMoving(null);
                  }}
                />
              </div>
            )}

            {open && cancelling && (
              <form className="picker cancel-form" onSubmit={cancel}>
                <div className="picker-header">
                  <strong>Cancelar aula</strong>
                </div>
                <label className="field">
                  <span>Motivo do cancelamento (opcional)</span>
                  <textarea
                    value={cancelReason}
                    onChange={(e) => setCancelReason(e.target.value)}
                    placeholder="Ex.: professor doente, manutenção da sala…"
                    maxLength={255}
                    rows={3}
                    autoFocus
                  />
                  <small className="muted">{cancelReason.length}/255</small>
                </label>
                <p className="muted small">
                  {data.attendees_count > 0
                    ? `${data.attendees_count} aluno(s) previsto(s) não terão esta aula. Nenhuma aula do plano é debitada.`
                    : "Nenhum aluno previsto nesta aula."}{" "}
                  O cancelamento pode ser desfeito depois.
                </p>
                <div className="cancel-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => {
                      setCancelling(false);
                      setCancelReason("");
                    }}
                  >
                    Voltar
                  </button>
                  <button type="submit" className="btn btn-danger" disabled={busy}>
                    Confirmar cancelamento
                  </button>
                </div>
              </form>
            )}

            {completed && isAdmin && reopening && (
              <ConfirmPanel
                title="Reabrir aula"
                confirmLabel="Confirmar reabertura"
                busy={busy}
                onConfirm={reopen}
                onCancel={() => setReopening(false)}
              >
                <p>A aula volta a ficar pendente de finalização:</p>
                <ul className="confirm-list">
                  <li>as aulas debitadas dos planos dos alunos são devolvidas;</li>
                  <li>presenças e faltas voltam para pendente;</li>
                  <li>o valor do professor sai do relatório de pagamento até a aula ser finalizada de novo.</li>
                </ul>
                <p className="muted small">Reagendamentos feitos a partir desta aula continuam valendo.</p>
              </ConfirmPanel>
            )}

            <footer className="drawer-footer">
              {completed && isAdmin && !reopening && (
                <button className="btn" disabled={busy} onClick={() => setReopening(true)}>
                  Reabrir aula
                </button>
              )}
              {cancelled && (
                <button className="btn" disabled={busy} onClick={restore}>
                  Desfazer cancelamento
                </button>
              )}
              {open && !cancelling && (
                <button className="btn btn-danger-outline" disabled={busy} onClick={() => setCancelling(true)}>
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
