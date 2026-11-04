import type { Schemas } from "@pilates/api-client";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, call } from "../lib/api";
import { perWeekLabel } from "../lib/labels";
import { DateInput } from "./DateInput";
import { addDays, fmtDate, fmtHour, fmtShortDay, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { ErrorBox, Loading } from "./ui";

type Group = Schemas["ClassGroupDetail"];
type StudentSummary = Schemas["StudentSummary"];
type Mode = "fixed" | "single";

type Props = { group: Group; canEdit: boolean; onChanged: () => void };

/** Aba "Alunos" do modal da turma: alunos fixos e inclusão fixa (recorrente) ou avulsa (reagendamento). */
export function GroupStudents({ group, canEdit, onChanged }: Props) {
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [removing, setRemoving] = useState<StudentSummary | null>(null);
  const [removeFrom, setRemoveFrom] = useState(todayISO());
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    try {
      await action();
      setNotice(success);
      onChanged();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function removeFixed(student: StudentSummary) {
    const ok = await run(async () => {
      const detail = await call(api.GET("/api/v1/students/{student_id}", { params: { path: { student_id: student.id } } }));
      await call(
        api.PUT("/api/v1/students/{student_id}/schedule", {
          params: { path: { student_id: student.id } },
          body: {
            class_group_ids: detail.schedule.map((s) => s.class_group_id).filter((id) => id !== group.id),
            effective_from: removeFrom,
          },
        }),
      );
    }, `${student.name} sai da turma a partir de ${fmtDate(removeFrom)}.`);
    if (ok) setRemoving(null);
  }

  return (
    <div className="group-students-tab">
      <section>
        <h3 className="section-title">
          Alunos fixos{" "}
          <span className="muted small">
            ({group.enrolled_count}/{group.capacity})
          </span>
        </h3>
        {group.students.length === 0 && <p className="muted small">Nenhum aluno fixo nesta turma.</p>}
        <ul className="fixed-list">
          {group.students.map((s) => (
            <li key={s.id}>
              <Link to={`/alunos/${s.id}`}>{s.name}</Link>
              {canEdit &&
                (removing?.id === s.id ? (
                  <span className="inline-confirm">
                    <span className="muted small">sai a partir de</span>
                    <DateInput value={removeFrom} min={todayISO()} onChange={setRemoveFrom} />
                    <button className="btn btn-sm btn-danger-outline" disabled={busy} onClick={() => removeFixed(s)}>
                      Confirmar
                    </button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setRemoving(null)}>
                      ✕
                    </button>
                  </span>
                ) : (
                  <button className="btn btn-sm btn-ghost" onClick={() => setRemoving(s)}>
                    Remover
                  </button>
                ))}
            </li>
          ))}
        </ul>
      </section>

      {notice && <div className="alert alert-success">{notice}</div>}
      {error && <ErrorBox message={error} />}

      {canEdit && <AddStudent group={group} busy={busy} run={run} />}
    </div>
  );
}

/** Valor do seletor de origem para "sem aula de origem" (aula avulsa). */
const DROP_IN = "drop-in";

function AddStudent({ group, busy, run }: {
  group: Group;
  busy: boolean;
  run: (action: () => Promise<unknown>, success: string) => Promise<boolean>;
}) {
  const [mode, setMode] = useState<Mode>("fixed");
  const [q, setQ] = useState("");
  const [student, setStudent] = useState<StudentSummary | null>(null);
  const [effectiveFrom, setEffectiveFrom] = useState(todayISO());
  const [originChoice, setOrigin] = useState<string>("");
  const [target, setTarget] = useState<string>("");
  const [justification, setJustification] = useState("");

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
      student && mode === "single"
        ? call(api.GET("/api/v1/students/{student_id}/upcoming-lessons", { params: { path: { student_id: student.id } } }))
        : Promise.resolve([]),
    [student?.id, mode],
  );
  // Sem aulas para reagendar (ex.: plano sem recorrência), a inclusão só pode ser avulsa.
  const origin = originChoice || (upcoming.data && upcoming.data.length === 0 ? DROP_IN : "");
  // Próximas aulas desta turma (8 semanas) com vaga e que ainda não começaram
  const today = todayISO();
  const occurrences = useAsync(
    () =>
      call(
        api.GET("/api/v1/calendar", {
          params: { query: { date_from: today, date_to: toISO(addDays(new Date(), 56)), room_id: group.room.id } },
        }),
      ),
    [group.id],
  );
  const nowHour = new Date().getHours();
  const targets = (occurrences.data ?? []).filter(
    (e) =>
      e.kind === "lesson" &&
      e.class_group_id === group.id &&
      (e.status === "confirmed" || e.status === "inactive") &&
      e.available_spots > 0 &&
      (e.date > today || group.start_hour > nowHour),
  );

  const alreadyFixed = !!detail.data?.schedule.some((s) => s.class_group_id === group.id);
  const freeSlots = detail.data?.free_schedule_slots ?? 0;
  const originLesson = (upcoming.data ?? []).find((u) => `${u.class_group_id}|${u.date}` === origin);
  const dropIn = origin === DROP_IN;

  function pick(s: StudentSummary) {
    setStudent(s);
    setQ("");
    setOrigin("");
    setTarget("");
  }


  async function addFixed() {
    if (!student || !detail.data) return;
    const ids = [...detail.data.schedule.map((s) => s.class_group_id), group.id];
    await run(
      () =>
        call(
          api.PUT("/api/v1/students/{student_id}/schedule", {
            params: { path: { student_id: student.id } },
            body: { class_group_ids: ids, effective_from: effectiveFrom },
          }),
        ),
      `${student.name} entrou como aluno fixo a partir de ${fmtDate(effectiveFrom)}.`,
    ).then((ok) => ok && setStudent(null));
  }

  async function addSingle() {
    if (!student || !target || (!originLesson && !dropIn)) return;
    if (dropIn) {
      const ok = await run(
        () =>
          call(
            api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/drop-in", {
              params: { path: { class_group_id: group.id, lesson_date: target } },
              body: { student_id: student.id, justification: justification || null },
            }),
          ),
        `${student.name} incluído(a) como avulso em ${fmtDate(target)} nesta turma.`,
      );
      if (ok) {
        setStudent(null);
        setJustification("");
      }
      return;
    }
    if (!originLesson) return;
    await run(
      () =>
        call(
          api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/reschedule", {
            params: { path: { class_group_id: originLesson.class_group_id, lesson_date: originLesson.date } },
            body: {
              student_id: student.id,
              target_class_group_id: group.id,
              target_date: target,
              justification: justification || null,
            },
          }),
        ),
      `${student.name} reagendado(a) de ${fmtDate(originLesson.date)} para ${fmtDate(target)} nesta turma.`,
    ).then((ok) => {
      if (ok) {
        setStudent(null);
        setJustification("");
      }
    });
  }

  return (
    <section className="add-student">
      <div className="card-title-row">
        <h3 className="section-title">Adicionar aluno</h3>
        <div className="segmented" role="group" aria-label="Tipo de inclusão">
          <button type="button" className={`seg ${mode === "fixed" ? "seg-present is-on" : ""}`} onClick={() => setMode("fixed")}>
            Fixo (recorrente)
          </button>
          <button
            type="button"
            className={`seg ${mode === "single" ? "seg-rescheduled is-on" : ""}`}
            onClick={() => setMode("single")}
          >
            Avulso (uma aula)
          </button>
        </div>
      </div>
      <p className="muted small">
        {mode === "fixed"
          ? "O aluno passa a ter esta turma no horário padrão, toda semana, respeitando o limite do plano."
          : "Inclui o aluno em uma data desta turma sem mudar o horário padrão: como reposição de outra aula dele ou como aula avulsa, que usa uma aula do plano (ex.: plano sem recorrência)."}
      </p>

      {student ? (
        <div className="picked-student">
          <span>
            <strong>{student.name}</strong>
            {detail.data && (
              <span className="muted small">
                {" "}
                · {detail.data.subscription ? `${detail.data.subscription.plan_name} (${perWeekLabel(detail.data.subscription.sessions_per_week, true)})` : "sem plano"}
                {" "}· {detail.data.schedule.length} turma(s) fixa(s) · {detail.data.credits_remaining} aula(s) restante(s)
              </span>
            )}
          </span>
          <button className="btn btn-sm btn-ghost" onClick={() => setStudent(null)}>
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
                  <button type="button" onClick={() => pick(s)}>
                    {s.name} <span className="muted small">{s.phones[0] ?? ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {student && detail.loading && !detail.data && <Loading />}

      {student && detail.data && mode === "fixed" && (
        <div className="add-form">
          {alreadyFixed ? (
            <p className="alert alert-info">{student.name} já é aluno fixo desta turma.</p>
          ) : detail.data.subscription?.sessions_per_week === 0 ? (
            <p className="alert alert-warning">
              O plano de {student.name} não tem recorrência. Use <strong>Avulso (uma aula)</strong> para incluí-lo nas aulas.
            </p>
          ) : freeSlots <= 0 ? (
            <p className="alert alert-warning">
              O plano de {student.name} não tem horário livre ({detail.data.schedule.length} turma(s) fixa(s)). Remova uma
              turma na ficha do aluno ou adicione como avulso.
            </p>
          ) : (
            <>
              <label className="field inline-field">
                <span>A partir de</span>
                <DateInput value={effectiveFrom} min={todayISO()} onChange={setEffectiveFrom} />
              </label>
              <button className="btn btn-primary" disabled={busy} onClick={addFixed}>
                Adicionar como fixo
              </button>
            </>
          )}
        </div>
      )}

      {student && mode === "single" && (
        <div className="add-form add-form-col">
          {upcoming.loading && !upcoming.data && <Loading />}
          {upcoming.data && (
            <>
              <div className="form-row">
                <label className="field">
                  <span>Aula de origem</span>
                  <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
                    <option value="">Selecione…</option>
                    <option value={DROP_IN}>Nenhuma: aula avulsa (usa 1 aula do plano)</option>
                    {upcoming.data.map((u) => (
                      <option key={`${u.class_group_id}|${u.date}`} value={`${u.class_group_id}|${u.date}`}>
                        {fmtShortDay(u.date)} {fmtHour(u.start_hour)} · {u.room}
                        {u.is_makeup ? " (reposição)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Data nesta turma</span>
                  <select value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="">Selecione…</option>
                    {targets.map((t) => (
                      <option key={t.date} value={t.date} disabled={originLesson?.class_group_id === group.id && originLesson.date === t.date}>
                        {fmtShortDay(t.date)} · {t.available_spots} vaga(s)
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="field">
                <span>{dropIn ? "Observação (opcional)" : "Justificativa (opcional)"}</span>
                <input value={justification} onChange={(e) => setJustification(e.target.value)} maxLength={500} />
              </label>
              <div>
                <button
                  className="btn btn-primary"
                  disabled={busy || !target || (!originLesson && !dropIn) || (dropIn && (detail.data?.credits_remaining ?? 0) <= 0)}
                  onClick={addSingle}
                >
                  {dropIn ? "Incluir como avulso" : "Reagendar para esta turma"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
