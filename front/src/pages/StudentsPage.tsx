import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { LessonPanel } from "../components/LessonPanel";
import { PlanHistory } from "../components/PlanHistory";
import { RenewPlanModal } from "../components/RenewPlanModal";
import { RescheduleTracking } from "../components/RescheduleTracking";
import { StudentFormModal } from "../components/StudentFormModal";
import { AttendanceHistory, ChangeLog, ScheduleHistory } from "../components/StudentHistory";
import { StudentServices } from "../components/StudentServices";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { addDays, fmtDate, fmtHour, fmtShortDay, money, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { subscriptionUsage, usageTone, perWeekLabel } from "../lib/labels";
import { useSession } from "../lib/session";

export function StudentsPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const { isAdmin } = useSession();
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
        {isAdmin && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + Novo aluno
          </button>
        )}
      </header>
      {creating && (
        <StudentFormModal
          onClose={() => setCreating(false)}
          onSaved={(id) => {
            setCreating(false);
            list.reload();
            navigate(`/alunos/${id}`);
          }}
        />
      )}

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
          {studentId ? (
            <StudentDetail id={Number(studentId)} onEdited={list.reload} />
          ) : (
            <Empty>Selecione um aluno para ver a ficha.</Empty>
          )}
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

function StudentDetail({ id, onEdited }: { id: number; onEdited: () => void }) {
  const student = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}", { params: { path: { student_id: id } } })),
    [id],
  );
  const [lesson, setLesson] = useState<{ groupId: number; date: string } | null>(null);
  const [renewing, setRenewing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showScheduleHistory, setShowScheduleHistory] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const { isAdmin } = useSession();
  if (student.loading && !student.data) return <Loading />;
  if (student.error) return <ErrorBox message={student.error} />;
  const s = student.data!;
  const sub = s.subscription;
  const usedPct = sub ? Math.min(100, (sub.credits_used / sub.total_classes) * 100) : 0;
  const refresh = () => {
    student.reload();
    setHistoryVersion((v) => v + 1);
  };

  return (
    <div className="stack">
      <div className="card profile">
        <span className="avatar avatar-lg">{initials(s.name)}</span>
        <div className="profile-main">
          <h2>{s.name}</h2>
          <p className="muted small">Aluno desde {fmtDate(s.created_at.slice(0, 10))}</p>
        </div>
        {isAdmin && (
          <button className="btn" onClick={() => setEditing(true)}>
            ✎ Editar
          </button>
        )}
      </div>
      {editing && (
        <StudentFormModal
          student={s}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            refresh();
            onEdited();
          }}
        />
      )}

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
          <div className="card-title-row">
            <h3 className="card-title">Plano em uso</h3>
            {isAdmin && s.is_active && (
              <button className="btn btn-sm" onClick={() => setRenewing(true)}>
                Renovar plano
              </button>
            )}
          </div>
          {sub ? (
            <>
              <div className="plan-head">
                <strong>{sub.plan_name ?? sub.plan.name}</strong>
                <Badge tone={usageTone[sub.usage]}>{subscriptionUsage[sub.usage]}</Badge>
              </div>
              <div className="progress" aria-label="Aulas utilizadas">
                <div className={`progress-bar ${usedPct >= 100 ? "is-full" : ""}`} style={{ width: `${usedPct}%` }} />
              </div>
              <p className="small">
                <strong>{sub.credits_remaining}</strong> de {sub.total_classes} aulas restantes ·{" "}
                {perWeekLabel(sub.sessions_per_week)}
              </p>
              <p className="small muted">
                {money(sub.final_price)}
                {Number(sub.discount_amount) > 0 && (
                  <>
                    {" "}
                    (de {money(sub.base_price)}, desconto {sub.discount_name})
                  </>
                )}{" "}
                · {money(sub.price_per_lesson)}/aula · contratado em {fmtDate(sub.start_date)}
              </p>
              <p className="small">
                {sub.is_paid ? (
                  <Badge tone="success">Pago{sub.paid_at && ` em ${fmtDate(sub.paid_at)}`}</Badge>
                ) : (
                  <Badge tone="warning">Pagamento pendente</Badge>
                )}
              </p>
              {s.queued_subscriptions.length > 0 && (
                <div className="queued">
                  <strong>Renovado antecipadamente:</strong>{" "}
                  {s.queued_subscriptions
                    .map((q) => `${q.plan_name ?? q.plan.name} (${q.total_classes} aulas)`)
                    .join(", ")}
                  . Começa a contar quando as aulas do plano em uso acabarem.
                </div>
              )}
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
                      ↻ {m.reschedule_count}x · original {fmtDate(m.original_date)} <span aria-hidden>›</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        <button className="btn btn-ghost btn-sm history-toggle" onClick={() => setShowScheduleHistory((v) => !v)}>
          {showScheduleHistory ? "▴ Ocultar histórico de horários" : "▾ Histórico de horários"}
        </button>
        {showScheduleHistory && <ScheduleHistory studentId={s.id} version={historyVersion} />}
      </div>

      <AttendanceHistory
        studentId={s.id}
        version={historyVersion}
        onOpenLesson={(groupId, date) => setLesson({ groupId, date })}
      />

      <RescheduleTracking
        studentId={s.id}
        version={historyVersion}
        onOpenLesson={(groupId, date) => setLesson({ groupId, date })}
      />

      <PlanHistory studentId={s.id} version={historyVersion} />

      <StudentServices
        studentId={s.id}
        active={s.is_active}
        version={historyVersion}
        onChanged={() => setHistoryVersion((v) => v + 1)}
      />

      <ChangeLog studentId={s.id} version={historyVersion} />

      {lesson && (
        <LessonPanel
          groupId={lesson.groupId}
          date={lesson.date}
          onClose={() => {
            setLesson(null);
            setHistoryVersion((v) => v + 1);
          }}
          onChanged={student.reload}
        />
      )}
      {renewing && (
        <RenewPlanModal
          student={s}
          onClose={() => setRenewing(false)}
          onSaved={() => {
            setRenewing(false);
            student.reload();
            setHistoryVersion((v) => v + 1);
          }}
        />
      )}
      <p className="muted small">
        <Link to="/">← Voltar para a agenda</Link>
      </p>
    </div>
  );
}
