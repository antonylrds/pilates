import { useState } from "react";

import { Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, fmtHour, money, toISO } from "../lib/format";
import { useAsync } from "../lib/hooks";

export function TeachersPage() {
  const now = new Date();
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [open, setOpen] = useState<number | null>(null);

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
          <p className="muted">Aulas dadas, alunos presentes e valor a receber</p>
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

          {report.data.teachers.length === 0 && <Empty>Nenhum professor cadastrado.</Empty>}

          <div className="stack">
            {report.data.teachers.map((t) => (
              <div key={t.teacher.id} className="card">
                <button className="teacher-row" onClick={() => setOpen(open === t.teacher.id ? null : t.teacher.id)}>
                  <span className="teacher-name">{t.teacher.name}</span>
                  <span className="muted small">
                    {money(t.pay_per_class)}/aula + {money(t.pay_per_student)}/aluno
                  </span>
                  <span className="small">
                    {t.lessons_given} aula(s) · {t.total_presences} presença(s)
                  </span>
                  <span className="teacher-amount">{money(t.amount)}</span>
                  <span className="muted" aria-hidden>
                    {open === t.teacher.id ? "▴" : "▾"}
                  </span>
                </button>
                {open === t.teacher.id && (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Data</th>
                        <th>Turma</th>
                        <th>Presentes</th>
                        <th className="num">Valor</th>
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
                            {l.present_students.map((s) => s.name).join(", ")}
                            {l.absent_students.length > 0 && (
                              <span className="muted small"> · faltas: {l.absent_students.map((s) => s.name).join(", ")}</span>
                            )}
                          </td>
                          <td className="num">{money(l.amount)}</td>
                        </tr>
                      ))}
                      {t.lessons.length === 0 && (
                        <tr>
                          <td colSpan={4} className="muted">
                            Nenhuma aula dada no período.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
