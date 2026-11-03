import type { Schemas } from "@pilates/api-client";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ReschedulePicker } from "../components/ReschedulePicker";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, fmtHour, fmtShortDay, fmtWeekday, parseISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { lessonStatus } from "../lib/labels";

type Entry = Schemas["CalendarEntry"];
type Choice = "present" | "absent" | "rescheduled";
type Decision = {
  status?: Choice;
  justification: string;
  target?: { class_group_id: number; date: string; label: string };
  picking?: boolean;
};

const hourOf = (iso: string) => Number(iso.slice(11, 13));

export function FinalizePage() {
  const { groupId, date } = useParams();
  return groupId && date ? <FinalizeForm groupId={Number(groupId)} date={date} /> : <PendingList />;
}

// ---------- Lista de aulas pendentes ----------
function daysAgo(date: string): number {
  return Math.round((parseISO(todayISO()).getTime() - parseISO(date).getTime()) / 86_400_000);
}

function PendingList() {
  const location = useLocation();
  const done = (location.state as { done?: string } | null)?.done;
  const pending = useAsync(() => call(api.GET("/api/v1/lessons/pending")), []);

  const byDate = new Map<string, Entry[]>();
  for (const e of pending.data ?? []) byDate.set(e.date, [...(byDate.get(e.date) ?? []), e]);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Finalizar aulas</h1>
          <p className="muted">
            Aulas que já começaram e aguardam a chamada. Só aulas concluídas contam em presenças, planos e pagamentos.
          </p>
        </div>
      </header>

      {done && <div className="alert alert-success">Aula “{done}” concluída.</div>}
      {pending.loading && !pending.data && <Loading />}
      {pending.error && <ErrorBox message={pending.error} />}
      {pending.data?.length === 0 && <Empty>Nenhuma aula pendente. Tudo em dia! 🎉</Empty>}

      <div className="stack">
        {[...byDate.entries()].map(([day, entries]) => {
          const ago = daysAgo(day);
          return (
            <section key={day} className="card">
              <div className="card-title-row">
                <h3 className="card-title day-title">{fmtWeekday(day)}</h3>
                <Badge tone={ago >= 2 ? "danger" : ago === 1 ? "warning" : "neutral"}>
                  {ago === 0 ? "Hoje" : ago === 1 ? "Ontem" : `Há ${ago} dias`}
                </Badge>
              </div>
              <ul className="pending-list">
                {entries.map((e) => (
                  <li key={e.class_group_id}>
                    <Link to={`/finalizar/${e.class_group_id}/${e.date}`} className="pending-item">
                      <span className="pending-time">{fmtHour(hourOf(e.starts_at))}</span>
                      <span>
                        <span className="list-title">{e.room.name}</span>
                        <span className="muted small"> · {e.teacher.name}</span>
                      </span>
                      <span className="muted small">{e.attendees_count} aluno(s)</span>
                      <span className="btn btn-sm btn-primary">Finalizar</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

// ---------- Formulário de finalização ----------
function FinalizeForm({ groupId, date }: { groupId: number; date: string }) {
  const navigate = useNavigate();
  const path = { class_group_id: groupId, lesson_date: date };
  const lesson = useAsync(
    () => call(api.GET("/api/v1/lessons/{class_group_id}/{lesson_date}", { params: { path } })),
    [groupId, date],
  );
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  if (lesson.loading && !lesson.data) return <div className="page"><Loading /></div>;
  if (lesson.error) return <div className="page"><ErrorBox message={lesson.error} /></div>;
  const data = lesson.data!;

  const expected = data.students.filter((s) => s.status !== "rescheduled");
  const preRescheduled = data.students.filter((s) => s.status === "rescheduled");
  const get = (id: number): Decision => decisions[id] ?? { justification: "" };
  const set = (id: number, patch: Partial<Decision>) =>
    setDecisions((d) => ({ ...d, [id]: { ...get(id), ...patch } }));

  const counts = { present: 0, absent: 0, rescheduled: 0, missing: 0 };
  for (const s of expected) {
    const d = get(s.student.id);
    if (!d.status || (d.status === "rescheduled" && !d.target)) counts.missing++;
    else counts[d.status]++;
  }
  const ready = expected.length > 0 && counts.missing === 0;

  async function submit() {
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.POST("/api/v1/lessons/{class_group_id}/{lesson_date}/complete", {
          params: { path },
          body: {
            items: expected.map((s) => {
              const d = get(s.student.id);
              return {
                student_id: s.student.id,
                status: d.status!,
                justification: d.status !== "present" && d.justification ? d.justification : null,
                target_class_group_id: d.status === "rescheduled" ? d.target!.class_group_id : null,
                target_date: d.status === "rescheduled" ? d.target!.date : null,
              };
            }),
          },
        }),
      );
      navigate("/finalizar", { state: { done: `${data.room.name} ${fmtDate(date)} ${fmtHour(hourOf(data.starts_at))}` } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page page-narrow">
      <p className="small">
        <Link to="/finalizar">← Aulas pendentes</Link>
      </p>
      <header className="page-header">
        <div>
          <div className="eyebrow">{fmtWeekday(date)}</div>
          <h1>
            {fmtHour(hourOf(data.starts_at))} · {data.room.name}
          </h1>
          <p className="muted">
            {data.teacher.name} · {expected.length} aluno(s) previsto(s)
          </p>
        </div>
        <Badge tone={data.status}>{lessonStatus[data.status]}</Badge>
      </header>

      {!data.can_complete ? (
        <div className="alert alert-info">
          {data.status === "completed"
            ? "Esta aula já foi concluída."
            : data.status === "cancelled"
              ? "Esta aula foi cancelada."
              : data.status === "inactive"
                ? "Esta aula não tem alunos previstos."
                : "Esta aula ainda não começou."}{" "}
          <Link to="/">Ver na agenda</Link>
        </div>
      ) : (
        <>
          <div className="finalize-toolbar">
            <button
              className="btn btn-sm"
              onClick={() =>
                setDecisions(
                  Object.fromEntries(expected.map((s) => [s.student.id, { ...get(s.student.id), status: "present" }])),
                )
              }
            >
              Marcar todos como presentes
            </button>
          </div>

          <ul className="stack">
            {expected.map((s) => {
              const d = get(s.student.id);
              return (
                <li key={s.student.id} className={`card finalize-row ${d.status ? `is-${d.status}` : ""}`}>
                  <div className="finalize-head">
                    <div>
                      <Link to={`/alunos/${s.student.id}`} className="roster-name">
                        {s.student.name}
                      </Link>
                      <div className="roster-meta">
                        {s.is_makeup && s.makeup_from && (
                          <Badge tone="warning">Reposição de {fmtDate(s.makeup_from.date)}</Badge>
                        )}
                        <span className={`small ${s.credits_remaining === 0 ? "text-danger" : "muted"}`}>
                          {s.credits_remaining === 0 ? "Sem aulas no plano" : `${s.credits_remaining} aula(s) no plano`}
                        </span>
                      </div>
                    </div>
                    <div className="segmented" role="group" aria-label={`Resultado de ${s.student.name}`}>
                      {(
                        [
                          ["present", "Presente"],
                          ["absent", "Falta"],
                          ["rescheduled", "Reagendar"],
                        ] as const
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          type="button"
                          className={`seg seg-${value} ${d.status === value ? "is-on" : ""}`}
                          aria-pressed={d.status === value}
                          onClick={() => set(s.student.id, { status: value, picking: value === "rescheduled" && !d.target })}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {(d.status === "absent" || d.status === "rescheduled") && (
                    <label className="field finalize-field">
                      <span>Justificativa (opcional)</span>
                      <input
                        value={d.justification}
                        onChange={(e) => set(s.student.id, { justification: e.target.value })}
                        placeholder={d.status === "absent" ? "Ex.: consulta médica, doente…" : "Ex.: viagem, compromisso…"}
                        maxLength={500}
                      />
                    </label>
                  )}

                  {d.status === "rescheduled" && (
                    <div className="finalize-field">
                      {d.target && !d.picking ? (
                        <div className="chosen">
                          <span>
                            Reposição: <strong>{d.target.label}</strong>
                          </span>
                          <button className="btn btn-sm btn-ghost" onClick={() => set(s.student.id, { picking: true })}>
                            Trocar
                          </button>
                        </div>
                      ) : (
                        <>
                          <span className="field-label">Escolha a aula de reposição</span>
                          <ReschedulePicker
                            fromGroupId={groupId}
                            fromDate={date}
                            selected={d.target}
                            onPick={(e) =>
                              set(s.student.id, {
                                picking: false,
                                target: {
                                  class_group_id: e.class_group_id,
                                  date: e.date,
                                  label: `${fmtShortDay(e.date)} ${fmtHour(hourOf(e.starts_at))} · ${e.room.name}`,
                                },
                              })
                            }
                          />
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {preRescheduled.length > 0 && (
            <div className="card muted-card">
              <h3 className="card-title">Reagendados antes da aula</h3>
              <ul className="stack-sm">
                {preRescheduled.map((s) => (
                  <li key={s.student.id} className="small">
                    <strong>{s.student.name}</strong>
                    {s.rescheduled_to && (
                      <>
                        {" "}
                        → {fmtDate(s.rescheduled_to.date)} {fmtHour(s.rescheduled_to.start_hour)}
                      </>
                    )}
                    {s.justification && <span className="muted"> · “{s.justification}”</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {error && <ErrorBox message={error} />}

          <div className="finalize-bar">
            <div className="finalize-summary">
              <span className="sum sum-present">{counts.present} presente(s)</span>
              <span className="sum sum-absent">{counts.absent} falta(s)</span>
              <span className="sum sum-rescheduled">{counts.rescheduled} reagendado(s)</span>
              {counts.missing > 0 && <span className="sum sum-missing">{counts.missing} pendente(s)</span>}
            </div>
            <button className="btn btn-primary" disabled={!ready || busy} onClick={submit}>
              {busy ? "Concluindo…" : "Concluir aula"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
