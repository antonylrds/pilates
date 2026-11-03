import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { Modal } from "../components/Modal";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, fmtHour, money, toISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

type Report = Schemas["TeacherPaymentReport"];
type Lesson = Schemas["TeacherLessonReport"];

const pct = (v: string | number) => `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

function lessonRule(l: Lesson): string {
  if (l.student_share_percent == null) return "Concluída na regra anterior (valor fixo por aluno)";
  return `Na conclusão: ${money(l.pay_per_class)}/aula + ${pct(l.student_share_percent)} do valor da aula do plano por aluno, mín. ${money(l.min_pay_per_lesson)}`;
}

export function TeachersPage() {
  const { isAdmin } = useSession();
  const now = new Date();
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [open, setOpen] = useState<number | null>(null);
  const [editing, setEditing] = useState<Report | null>(null);

  const [y, m] = month.split("-").map(Number);
  const dateFrom = toISO(new Date(y, m - 1, 1));
  const dateTo = toISO(new Date(y, m, 0));

  const report = useAsync(
    () =>
      call(api.GET("/api/v1/reports/teacher-payments", { params: { query: { date_from: dateFrom, date_to: dateTo } } })),
    [month],
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Professores</h1>
          <p className="muted">Aulas concluídas, alunos presentes e valor a receber</p>
        </div>
        <input type="month" className="input-month" value={month} onChange={(e) => setMonth(e.target.value)} />
      </header>

      {report.loading && !report.data && <Loading />}
      {report.error && <ErrorBox message={report.error} />}

      {report.data && (
        <>
          <div className="stats">
            <div className="stat">
              <span className="stat-label">Total a pagar</span>
              <span className="stat-value">{money(report.data.total_amount)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Aulas dadas</span>
              <span className="stat-value">{report.data.teachers.reduce((n, t) => n + t.lessons_given, 0)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Presenças</span>
              <span className="stat-value">{report.data.teachers.reduce((n, t) => n + t.total_presences, 0)}</span>
            </div>
          </div>

          <p className="muted small rule-note">
            Por aula concluída: valor fixo + para cada aluno presente um percentual do valor de uma aula do plano dele
            (preço pago ÷ aulas do plano), nunca abaixo do mínimo. Se todos faltarem, o professor recebe o mínimo. O
            valor fica congelado na conclusão; aulas não concluídas não contam.
          </p>

          {report.data.teachers.length === 0 && <Empty>Nenhum professor cadastrado.</Empty>}

          <div className="stack">
            {report.data.teachers.map((t) => (
              <div key={t.teacher.id} className="card">
                <div className="teacher-row">
                  <button
                    className="teacher-toggle"
                    onClick={() => setOpen(open === t.teacher.id ? null : t.teacher.id)}
                    aria-expanded={open === t.teacher.id}
                  >
                    <span className="teacher-name">{t.teacher.name}</span>
                    <span className="muted small">
                      {money(t.pay_per_class)}/aula + {pct(t.student_share_percent)} por aluno
                      {Number(t.min_pay_per_lesson) > 0 && <> · mín. {money(t.min_pay_per_lesson)}</>}
                      {" "}· serviços {pct(t.service_share_percent)}
                    </span>
                    <span className="small">
                      {t.lessons_given} aula(s) · {t.total_presences} presença(s)
                      {t.lessons_without_presence > 0 && (
                        <span className="muted"> · {t.lessons_without_presence} sem presença</span>
                      )}
                      {t.services.length > 0 && (
                        <span className="muted">
                          {" "}
                          · ✚ {t.services_given} atendimento(s) {money(t.services_amount)}
                        </span>
                      )}
                    </span>
                    <span className="teacher-amount">{money(t.amount)}</span>
                    <span className="muted" aria-hidden>
                      {open === t.teacher.id ? "▴" : "▾"}
                    </span>
                  </button>
                  {isAdmin && (
                    <button className="btn btn-sm" onClick={() => setEditing(t)}>
                      Valores
                    </button>
                  )}
                </div>
                {open === t.teacher.id && (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Data</th>
                        <th>Sala</th>
                        <th>Presentes (valor gerado)</th>
                        <th className="num">Valor da aula</th>
                      </tr>
                    </thead>
                    <tbody>
                      {t.lessons.map((l) => (
                        <tr key={`${l.class_group_id}-${l.date}`}>
                          <td>
                            {fmtDate(l.date)} {fmtHour(l.start_hour)}
                          </td>
                          <td>{l.room}</td>
                          <td>
                            {l.present_students.length > 0 ? (
                              <ul className="present-list">
                                {l.present_students.map((s) => (
                                  <li key={s.id} title={s.plan ? `Plano: ${s.plan}` : "Sem aula disponível no plano"}>
                                    {s.name}
                                    {s.amount != null && <span className="muted"> · {money(s.amount)}</span>}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-danger">Todos ausentes</span>
                            )}
                            {l.absent_students.length > 0 && (
                              <span className="muted small">faltas: {l.absent_students.map((s) => s.name).join(", ")}</span>
                            )}
                          </td>
                          <td className="num" title={lessonRule(l)}>
                            {l.minimum_applied && <Badge tone="info">mínimo</Badge>} {money(l.amount)}
                          </td>
                        </tr>
                      ))}
                      {t.lessons.length === 0 && (
                        <tr>
                          <td colSpan={4} className="muted">
                            Nenhuma aula concluída no período.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
                {open === t.teacher.id && t.services.length > 0 && (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Data</th>
                        <th>Serviço avulso</th>
                        <th>Cliente</th>
                        <th className="num">Valor ao profissional</th>
                      </tr>
                    </thead>
                    <tbody>
                      {t.services.map((s) => (
                        <tr key={s.session_id}>
                          <td>
                            {fmtDate(s.date)} {fmtHour(s.start_hour)}
                          </td>
                          <td>
                            ✚ {s.service_name} <span className="muted small">· {s.room}</span>
                          </td>
                          <td>
                            {s.student.name}
                            {!s.present && <span className="text-danger small"> · falta</span>}
                          </td>
                          <td className="num" title={`${pct(s.share_percent)} de ${money(s.price)}`}>
                            {money(s.amount)}
                          </td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={3} className="muted small">
                          Aulas {money(t.lessons_amount)} + serviços {money(t.services_amount)}
                        </td>
                        <td className="num">
                          <strong>{money(t.amount)}</strong>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {editing && (
        <PayModal
          report={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            report.reload();
          }}
        />
      )}
    </div>
  );
}

function PayModal({ report, onClose, onSaved }: { report: Report; onClose: () => void; onSaved: () => void }) {
  const plans = useAsync(() => call(api.GET("/api/v1/plans")), []);
  const [perClass, setPerClass] = useState(report.pay_per_class);
  const [percent, setPercent] = useState(report.student_share_percent);
  const [minimum, setMinimum] = useState(report.min_pay_per_lesson);
  const [servicePercent, setServicePercent] = useState(report.service_share_percent);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const perStudent = (plan: Schemas["PlanRead"]) => (Number(plan.price) / plan.total_classes) * (Number(percent || 0) / 100);
  const lessonValue = (studentsTotal: number, presences: number) =>
    Math.max(presences > 0 ? Number(perClass || 0) + studentsTotal : 0, Number(minimum || 0));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.PATCH("/api/v1/teachers/{teacher_id}", {
          params: { path: { teacher_id: report.teacher.id } },
          body: {
            pay_per_class: perClass || "0",
            student_share_percent: percent || "0",
            min_pay_per_lesson: minimum || "0",
            service_share_percent: servicePercent || "0",
          },
        }),
      );
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const prefixed = (prefix: string, value: string, set: (v: string) => void, max?: number) => (
    <div className="input-money">
      <span>{prefix}</span>
      <input type="number" min={0} max={max} step="0.01" value={value} onChange={(e) => set(e.target.value)} />
    </div>
  );

  const firstPlan = plans.data?.[0];

  return (
    <Modal
      title={`Remuneração · ${report.teacher.name}`}
      subtitle="Vale para as aulas concluídas a partir de agora. Aulas já concluídas mantêm os valores da época."
      onClose={onClose}
      footer={
        <button type="submit" form="pay-form" className="btn btn-primary" disabled={busy}>
          Salvar
        </button>
      }
    >
      <form id="pay-form" onSubmit={save}>
        <div className="form-row">
          <label className="field">
            <span>Valor fixo por aula</span>
            {prefixed("R$", perClass, setPerClass)}
            <small className="muted">Pago por aula concluída com alunos presentes</small>
          </label>
          <label className="field">
            <span>% por aluno presente</span>
            {prefixed("%", percent, setPercent, 100)}
            <small className="muted">Do valor de uma aula do plano do aluno</small>
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>Valor mínimo por aula</span>
            {prefixed("R$", minimum, setMinimum)}
            <small className="muted">Garantido por aula concluída, inclusive quando todos os alunos faltam</small>
          </label>
          <label className="field">
            <span>% em serviços avulsos</span>
            {prefixed("%", servicePercent, setServicePercent, 100)}
            <small className="muted">Do valor da sessão (fisioterapia, RPG…), quando o cliente comparece</small>
          </label>
        </div>
      </form>

      <div className="pay-examples">
        <span className="field-label">Valor por aluno presente, por plano</span>
        {plans.loading && !plans.data && <Loading />}
        <ul>
          {(plans.data ?? []).map((p) => (
            <li key={p.id}>
              <span>
                {p.name} <span className="muted small">({money(p.price)} ÷ {p.total_classes} aulas)</span>
              </span>
              <strong>{money(perStudent(p))}</strong>
            </li>
          ))}
        </ul>
        {firstPlan && (
          <>
            <span className="field-label pay-examples-sub">Simulação de uma aula ({firstPlan.name})</span>
            <ul>
              {[0, 1, 3].map((n) => (
                <li key={n}>
                  <span>{n === 0 ? "Todos faltaram" : `${n} aluno(s) presente(s)`}</span>
                  <strong>{money(lessonValue(perStudent(firstPlan) * n, n))}</strong>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="muted small">Descontos reduzem o valor de referência (usa o preço pago pelo aluno).</p>
      </div>
      {error && <ErrorBox message={error} />}
    </Modal>
  );
}
