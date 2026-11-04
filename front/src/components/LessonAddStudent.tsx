import type { Schemas } from "@pilates/api-client";
import { useState } from "react";

import { api, call } from "../lib/api";
import { fmtShortDay, fmtHour } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { perWeekLabel } from "../lib/labels";
import { Loading } from "./ui";

type Lesson = Schemas["LessonDetail"];
type StudentSummary = Schemas["StudentSummary"];
type Mode = "drop-in" | "makeup";

type Props = {
  groupId: number;
  date: string;
  lesson: Lesson;
  busy: boolean;
  run: (action: () => Promise<unknown>) => Promise<boolean>;
};

/**
 * Inclui um aluno nesta aula (agenda → detalhes da aula):
 * - aula avulsa: usa uma aula do plano; bloqueado se o aluno não tiver aulas disponíveis;
 * - reposição: traz uma aula futura do aluno para esta data (não usa aula a mais).
 */
export function LessonAddStudent({ groupId, date, lesson, busy, run }: Props) {
  const [openForm, setOpenForm] = useState(false);
  const [mode, setMode] = useState<Mode>("drop-in");
  const [q, setQ] = useState("");
  const [student, setStudent] = useState<StudentSummary | null>(null);
  const [origin, setOrigin] = useState("");
  const [note, setNote] = useState("");

  const inLesson = new Set(lesson.students.map((s) => s.student.id));
  const results = useAsync(
    () => (q.trim().length < 2 ? Promise.resolve([]) : call(api.GET("/api/v1/students", { params: { query: { q, limit: 8 } } }))),
    [q],
  );
  const detail = useAsync(
    () =>
      student
        ? call(api.GET("/api/v1/students/{student_id}", { params: { path: { student_id: student.id } } }))
        : Promise.resolve(null),
    [student?.id],
  );
  const upcoming = useAsync(
    () =>
      student && mode === "makeup"
        ? call(api.GET("/api/v1/students/{student_id}/upcoming-lessons", { params: { path: { student_id: student.id } } }))
        : Promise.resolve([]),
    [student?.id, mode],
  );
  const origins = (upcoming.data ?? []).filter((u) => !(u.class_group_id === groupId && u.date === date));
  const originLesson = origins.find((u) => `${u.class_group_id}|${u.date}` === origin);

  function reset() {
    setStudent(null);
    setQ("");
    setOrigin("");
    setNote("");
  }

  if (!openForm) {
    return (
      <button className="btn btn-block add-student-toggle" onClick={() => setOpenForm(true)} disabled={lesson.available_spots <= 0}>
        {lesson.available_spots > 0 ? "+ Incluir aluno nesta aula" : "Aula lotada"}
      </button>
    );
  }

  const d = detail.data;
  // Bloqueio por falta de aulas: avulsa usa uma aula a mais; reposição precisa de saldo para ser debitada.
  const noLessons =
    !!d && (mode === "drop-in" ? d.drop_in_available <= 0 : d.credits_remaining <= 0);
  const reserved = d ? d.credits_remaining - d.drop_in_available : 0;

  async function submit() {
    if (!student || noLessons) return;
    const ok =
      mode === "drop-in"
        ? await run(() =>
            call(
              api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/drop-in", {
                params: { path: { class_group_id: groupId, lesson_date: date } },
                body: { student_id: student.id, justification: note || null },
              }),
            ),
          )
        : originLesson
          ? await run(() =>
              call(
                api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule", {
                  params: { path: { class_group_id: originLesson.class_group_id, lesson_date: originLesson.date } },
                  body: { student_id: student.id, target_class_group_id: groupId, target_date: date, justification: note || null },
                }),
              ),
            )
          : false;
    if (ok) {
      reset();
      setOpenForm(false);
    }
  }

  return (
    <section className="picker lesson-add">
      <div className="picker-header">
        <strong>Incluir aluno</strong>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            reset();
            setOpenForm(false);
          }}
        >
          Fechar
        </button>
      </div>

      <div className="segmented" role="group" aria-label="Tipo de inclusão">
        <button type="button" className={`seg ${mode === "drop-in" ? "seg-present is-on" : ""}`} onClick={() => setMode("drop-in")}>
          Aula avulsa
        </button>
        <button type="button" className={`seg ${mode === "makeup" ? "seg-rescheduled is-on" : ""}`} onClick={() => setMode("makeup")}>
          Reposição de outra aula
        </button>
      </div>
      <p className="muted small">
        {mode === "drop-in"
          ? "O aluno entra só nesta data e usa uma aula do plano. O horário padrão não muda."
          : "Traz uma aula futura do aluno para esta data. Não usa aula a mais do plano."}
      </p>

      {student ? (
        <div className="picked-student">
          <span>
            <strong>{student.name}</strong>
            {d && (
              <span className="muted small">
                {" "}
                · {d.subscription ? `${d.subscription.plan_name} (${perWeekLabel(d.subscription.sessions_per_week, true)})` : "sem plano"}
                {" "}· {d.credits_remaining} aula(s) restante(s)
                {reserved > 0 && <> · {reserved} já reservada(s) como avulsa</>}
              </span>
            )}
          </span>
          <button className="btn btn-sm btn-ghost" onClick={reset}>
            Trocar
          </button>
        </div>
      ) : (
        <div className="student-search">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar aluno por nome, telefone ou e-mail" autoFocus />
          {(results.data ?? []).length > 0 && (
            <ul className="search-results">
              {(results.data ?? []).map((s) => (
                <li key={s.id}>
                  <button type="button" disabled={inLesson.has(s.id)} onClick={() => setStudent(s)}>
                    {s.name}{" "}
                    <span className="muted small">{inLesson.has(s.id) ? "já está nesta aula" : (s.phones[0] ?? "")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {student && detail.loading && !d && <Loading />}

      {student && d && noLessons && (
        <p className="alert alert-error" role="alert">
          {mode === "drop-in" && d.credits_remaining > 0
            ? `${student.name} não tem aulas disponíveis: as ${d.credits_remaining} aula(s) restante(s) já estão reservadas em outras aulas avulsas.`
            : `${student.name} não tem aulas disponíveis no plano.`}{" "}
          Renove o plano na ficha do aluno para incluí-lo.
        </p>
      )}

      {student && d && !noLessons && (
        <div className="add-form add-form-col">
          {mode === "makeup" && (
            <>
              {upcoming.loading && !upcoming.data && <Loading />}
              {upcoming.data && origins.length === 0 && (
                <p className="alert alert-warning">{student.name} não tem aulas futuras para trazer para esta data.</p>
              )}
              {origins.length > 0 && (
                <label className="field">
                  <span>Aula de origem</span>
                  <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
                    <option value="">Selecione…</option>
                    {origins.map((u) => (
                      <option key={`${u.class_group_id}|${u.date}`} value={`${u.class_group_id}|${u.date}`}>
                        {fmtShortDay(u.date)} {fmtHour(u.start_hour)} · {u.room}
                        {u.is_makeup ? " (reposição)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          )}
          <label className="field">
            <span>{mode === "drop-in" ? "Observação (opcional)" : "Justificativa (opcional)"}</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Ex.: aula experimental" />
          </label>
          <div>
            <button className="btn btn-primary" disabled={busy || (mode === "makeup" && !originLesson)} onClick={submit}>
              {mode === "drop-in" ? "Incluir como avulso" : "Trazer para esta aula"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
