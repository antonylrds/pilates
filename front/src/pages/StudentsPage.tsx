import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { LessonPanel } from "../components/LessonPanel";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { addDays, fmtDate, fmtHour, fmtShortDay, money, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { subscriptionStatus } from "../lib/labels";

export function StudentsPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const list = useAsync(
    () => call(api.GET("/api/v1/students", { params: { query: { q: q || undefined } } })),
    [q],
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Alunos</h1>
          <p className="muted">{list.data ? `${list.data.length} aluno(s) ativo(s)` : " "}</p>
        </div>
      </header>

      <div className="split">
        <section className="card list-card">
          <input
            className="search"
            placeholder="Buscar por nome, telefone ou e-mail"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {list.error && <ErrorBox message={list.error} />}
          <ul className="list">
            {(list.data ?? []).map((s) => (
              <li key={s.id}>
                <button
                  className={`list-item ${String(s.id) === studentId ? "is-active" : ""}`}
                  onClick={() => navigate(`/alunos/${s.id}`)}
                >
                  <span className="avatar">{initials(s.name)}</span>
                  <span>
                    <span className="list-title">{s.name}</span>
                    <span className="muted small">{s.phones[0] ?? s.emails[0] ?? "—"}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="detail">
          {studentId ? <StudentDetail id={Number(studentId)} /> : <Empty>Selecione um aluno para ver a ficha.</Empty>}
        </section>
      </div>
    </div>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}

/** Próxima data (>= hoje e >= início do horário) em que a turma acontece; pula a aula de hoje se já terminou. */
function nextOccurrence(weekday: number, startHour: number, startDate: string): string {
  const today = todayISO();
  let base = parseISO(startDate > today ? startDate : today);
  const baseWeekday = (base.getDay() + 6) % 7; // segunda = 0
  let diff = (weekday - baseWeekday + 7) % 7;
  if (diff === 0 && toISO(base) === today && new Date().getHours() >= startHour + 1) diff = 7;
  base = addDays(base, diff);
  return toISO(base);
}

function StudentDetail({ id }: { id: number }) {
  const student = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}", { params: { path: { student_id: id } } })),
    [id],
  );
  const [lesson, setLesson] = useState<{ groupId: number; date: string } | null>(null);
  if (student.loading && !student.data) return <Loading />;
  if (student.error) return <ErrorBox message={student.error} />;
  const s = student.data!;
  const sub = s.subscription;
  const usedPct = sub ? Math.min(100, (sub.credits_used / sub.total_classes) * 100) : 0;

  return (
    <div className="stack">
      <div className="card profile">
        <span className="avatar avatar-lg">{initials(s.name)}</span>
        <div>
          <h2>{s.name}</h2>
          <p className="muted small">Aluno desde {fmtDate(s.created_at.slice(0, 10))}</p>
        </div>
      </div>

      {s.needs_renewal && (
        <div className="alert alert-warning">
          <strong>Renovação necessária.</strong> As aulas do plano se esgotaram.
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <h3 className="card-title">Contato</h3>
          <dl className="facts facts-stacked">
            <div>
              <dt>Telefones</dt>
              <dd>{s.phones.length ? s.phones.join(" · ") : "—"}</dd>
            </div>
            <div>
              <dt>E-mails</dt>
              <dd>{s.emails.length ? s.emails.join(" · ") : "—"}</dd>
            </div>
            <div>
              <dt>Observações</dt>
              <dd>{s.notes || "—"}</dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h3 className="card-title">Plano</h3>
          {sub ? (
            <>
              <div className="plan-head">
                <strong>{sub.plan.name}</strong>
                <Badge tone={sub.status === "active" ? "success" : "danger"}>{subscriptionStatus[sub.status]}</Badge>
              </div>
              <div className="progress" aria-label="Aulas utilizadas">
                <div className={`progress-bar ${usedPct >= 100 ? "is-full" : ""}`} style={{ width: `${usedPct}%` }} />
              </div>
              <p className="small">
                <strong>{sub.credits_remaining}</strong> de {sub.total_classes} aulas restantes ·{" "}
                {sub.sessions_per_week}x por semana
              </p>
              <p className="small muted">
                {money(sub.final_price)}
                {Number(sub.discount_amount) > 0 && (
                  <>
                    {" "}
                    (de {money(sub.base_price)}, desconto {sub.discount?.name})
                  </>
                )}{" "}
                · início {fmtDate(sub.start_date)}
              </p>
            </>
          ) : (
            <p className="muted">Sem plano vinculado.</p>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">
          Turmas padrão{" "}
          {s.free_schedule_slots > 0 && (
            <span className="muted small">({s.free_schedule_slots} horário(s) disponível(is) no plano)</span>
          )}
        </h3>
        {s.schedule.length === 0 && <p className="muted">Nenhuma turma.</p>}
        <ul className="slots">
          {s.schedule.map((g) => {
            const next = nextOccurrence(g.weekday, g.start_hour, g.start_date);
            return (
              <li key={g.enrollment_id}>
                <button
                  className="slot slot-link"
                  onClick={() => setLesson({ groupId: g.class_group_id, date: next })}
                  title="Ver detalhes da próxima aula"
                >
                  <span className="slot-day">{g.weekday_name}</span>
                  <span className="slot-time">
                    {fmtHour(g.start_hour)} – {fmtHour(g.end_hour)}
                  </span>
                  <span className="muted small">
                    {g.room} · {g.teacher}
                  </span>
                  <span className="slot-next">
                    Próxima: {fmtShortDay(next)} <span aria-hidden>›</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {s.upcoming_makeups.length > 0 && (
          <>
            <h4 className="subhead">Reposições agendadas</h4>
            <ul className="slots">
              {s.upcoming_makeups.map((m) => (
                <li key={`${m.class_group_id}-${m.date}`}>
                  <button
                    className="slot slot-link slot-makeup"
                    onClick={() => setLesson({ groupId: m.class_group_id, date: m.date })}
                    title="Ver detalhes da aula de reposição"
                  >
                    <span className="slot-day">{fmtDate(m.date)}</span>
                    <span className="slot-time">{fmtHour(m.start_hour)}</span>
                    <span className="muted small">{m.room}</span>
                    <span className="slot-next">
                      Ver aula <span aria-hidden>›</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {lesson && (
        <LessonPanel
          groupId={lesson.groupId}
          date={lesson.date}
          onClose={() => setLesson(null)}
          onChanged={student.reload}
        />
      )}
      <p className="muted small">
        <Link to="/">← Voltar para a agenda</Link>
      </p>
    </div>
  );
}
