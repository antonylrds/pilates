import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { DateInput } from "../components/DateInput";
import { Modal } from "../components/Modal";
import { PaymentActionModal, type PaymentAction } from "../components/PaymentActionModal";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, money, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

type Payment = Schemas["PaymentRead"];
type Kind = Payment["kind"];
type Status = Payment["status"];
type DateField = "created" | "paid" | "cancelled";

const KIND_LABEL: Record<Kind, string> = { student: "Aluno", teacher: "Professor" };
const STATUS_LABEL: Record<Status, string> = { pending: "Pendente", paid: "Pago", cancelled: "Cancelado" };
const STATUS_TONE: Record<Status, string> = { pending: "warning", paid: "success", cancelled: "danger" };
const DATE_FIELD_LABEL: Record<DateField, string> = { created: "Criação", paid: "Pagamento", cancelled: "Cancelamento" };

/** Todos os pagamentos do estúdio (alunos e professores), com filtros e ações. */
export function PaymentsPage() {
  const { isAdmin } = useSession();
  const [kind, setKind] = useState<Kind | "">("");
  const [status, setStatus] = useState<Status | "">("");
  const [studentId, setStudentId] = useState<number | "">("");
  const [dateField, setDateField] = useState<DateField>("created");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [action, setAction] = useState<PaymentAction>();
  const [creating, setCreating] = useState(false);

  const students = useAsync(() => (isAdmin ? call(api.GET("/api/v1/students", { params: { query: { is_active: null, limit: 500 } } })) : Promise.resolve([])), [isAdmin]);
  const invalidRange = Boolean(dateFrom && dateTo && dateTo < dateFrom);
  const list = useAsync(
    () =>
      isAdmin && !invalidRange
        ? call(
            api.GET("/api/v1/payments", {
              params: {
                query: {
                  kind: kind || undefined,
                  status: status || undefined,
                  student_id: studentId === "" ? undefined : studentId,
                  date_field: dateField,
                  date_from: dateFrom || undefined,
                  date_to: dateTo || undefined,
                  limit: 500,
                },
              },
            }),
          )
        : Promise.resolve(null),
    [isAdmin, kind, status, studentId, dateField, dateFrom, dateTo],
  );

  if (!isAdmin) {
    return (
      <div className="page">
        <h1>Pagamentos</h1>
        <p className="alert alert-warning">Apenas administradores podem ver os pagamentos do estúdio.</p>
      </div>
    );
  }

  const data = list.data;
  const hasFilters = Boolean(kind || status || studentId !== "" || dateFrom || dateTo);
  const clear = () => {
    setKind("");
    setStatus("");
    setStudentId("");
    setDateFrom("");
    setDateTo("");
  };
  const done = () => {
    setAction(undefined);
    setCreating(false);
    list.reload();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Pagamentos</h1>
          <p className="muted">Planos dos alunos e repasses aos professores</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          Novo pagamento
        </button>
      </header>

      <section className="card">
        <div className="form-row-3">
          <label className="field">
            <span>Tipo</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as Kind | "")}>
              <option value="">Todos</option>
              <option value="student">Aluno</option>
              <option value="teacher">Professor</option>
            </select>
          </label>
          <label className="field">
            <span>Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as Status | "")}>
              <option value="">Todos</option>
              {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Aluno</span>
            <select value={studentId} onChange={(e) => setStudentId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Todos</option>
              {(students.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row-3">
          <label className="field">
            <span>Filtrar datas por</span>
            <select value={dateField} onChange={(e) => setDateField(e.target.value as DateField)}>
              {(Object.keys(DATE_FIELD_LABEL) as DateField[]).map((f) => (
                <option key={f} value={f}>
                  {DATE_FIELD_LABEL[f]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>De</span>
            <DateInput value={dateFrom} onChange={setDateFrom} aria-label="Data inicial" />
          </label>
          <label className="field">
            <span>Até</span>
            <DateInput value={dateTo} onChange={setDateTo} aria-label="Data final" />
          </label>
        </div>
        {invalidRange && <p className="alert alert-warning">A data final deve ser igual ou posterior à inicial.</p>}
        {hasFilters && (
          <button className="btn btn-ghost btn-sm" onClick={clear}>
            Limpar filtros
          </button>
        )}
      </section>

      {list.loading && !data && <Loading />}
      {list.error && <ErrorBox message={list.error} />}

      {data && (
        <>
          <div className="stats">
            <div className="stat">
              <span className="stat-label">Pendente</span>
              <span className="stat-value">{money(data.totals.pending)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Pago</span>
              <span className="stat-value text-success">{money(data.totals.paid)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Cancelado</span>
              <span className="stat-value">{money(data.totals.cancelled)}</span>
            </div>
          </div>

          <section className="card">
            <h3 className="card-title">
              Pagamentos <span className="muted small">({data.count})</span>
            </h3>
            {data.items.length === 0 ? (
              <Empty>Nenhum pagamento encontrado.</Empty>
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Criado em</th>
                      <th>Tipo</th>
                      <th>Quem / referência</th>
                      <th className="num">Valor</th>
                      <th>Status</th>
                      <th>Pago em</th>
                      <th>Cancelado em</th>
                      <th>Observações</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((p) => (
                      <tr key={p.id}>
                        <td>{fmtDate(p.created_at)}</td>
                        <td>
                          <Badge tone={p.kind === "student" ? "info" : "neutral"}>{KIND_LABEL[p.kind]}</Badge>
                        </td>
                        <td>
                          {p.student ? (
                            <>
                              <Link to={`/alunos/${p.student.id}`}>{p.student.name}</Link>
                              <div className="muted small">{p.plan_name}</div>
                            </>
                          ) : (
                            <>
                              {p.teacher?.name}
                              {p.period_start && p.period_end && (
                                <div className="muted small">
                                  {fmtDate(p.period_start)} a {fmtDate(p.period_end)}
                                </div>
                              )}
                            </>
                          )}
                        </td>
                        <td className="num">
                          <strong>{money(p.amount)}</strong>
                        </td>
                        <td>
                          <Badge tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Badge>
                        </td>
                        <td>{p.paid_at ? fmtDate(p.paid_at) : "—"}</td>
                        <td>{p.cancelled_at ? fmtDate(p.cancelled_at) : "—"}</td>
                        <td className="small">{p.notes || <span className="muted">—</span>}</td>
                        <td>
                          <div className="toolbar">
                            {p.status !== "paid" && p.status !== "cancelled" && (
                              <button className="btn btn-sm btn-primary" onClick={() => setAction({ payment: p, type: "pay" })}>
                                Pagar
                              </button>
                            )}
                            {p.status === "paid" && (
                              <button className="btn btn-sm" onClick={() => setAction({ payment: p, type: "pending" })}>
                                Voltar a pendente
                              </button>
                            )}
                            {p.status !== "cancelled" && (
                              <button className="btn btn-sm" onClick={() => setAction({ payment: p, type: "cancel" })}>
                                Cancelar
                              </button>
                            )}
                            <button className="btn btn-sm btn-ghost" onClick={() => setAction({ payment: p, type: "notes" })}>
                              Observações
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {data.count > data.items.length && (
              <p className="muted small">Mostrando {data.items.length} de {data.count}. Use os filtros para refinar.</p>
            )}
          </section>
        </>
      )}

      {action && <PaymentActionModal action={action} onClose={() => setAction(undefined)} onDone={done} />}
      {creating && <CreateModal onClose={() => setCreating(false)} onDone={done} />}
    </div>
  );
}

function CreateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState<Kind>("student");
  const students = useAsync(() => call(api.GET("/api/v1/students", { params: { query: { limit: 500 } } })), []);
  const teachers = useAsync(() => call(api.GET("/api/v1/teachers")), []);
  const [studentId, setStudentId] = useState<number | "">("");
  const [subscriptionId, setSubscriptionId] = useState<number | "">("");
  const [teacherId, setTeacherId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [isPaid, setIsPaid] = useState(false);
  const [paidAt, setPaidAt] = useState(todayISO());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const subscriptions = useAsync(
    () =>
      studentId === ""
        ? Promise.resolve([])
        : call(api.GET("/api/v1/students/{student_id}/subscriptions", { params: { path: { student_id: studentId } } })),
    [studentId],
  );
  // Um plano só pode ter um pagamento ativo: oferece os que ainda não têm (não pagos e não cancelados).
  const options = (subscriptions.data ?? []).filter((s) => s.status !== "cancelled" && !s.is_paid);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.POST("/api/v1/payments", {
          body:
            kind === "student"
              ? {
                  kind,
                  student_id: studentId === "" ? null : studentId,
                  subscription_id: subscriptionId === "" ? null : subscriptionId,
                  is_paid: isPaid,
                  paid_at: isPaid ? paidAt : null,
                  notes: notes || null,
                }
              : {
                  kind,
                  teacher_id: teacherId === "" ? null : teacherId,
                  amount: amount.replace(",", "."),
                  period_start: periodStart || null,
                  period_end: periodEnd || null,
                  is_paid: isPaid,
                  paid_at: isPaid ? paidAt : null,
                  notes: notes || null,
                },
        }),
      );
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Novo pagamento"
      onClose={onClose}
      footer={
        <button type="submit" form="payment-form" className="btn btn-primary" disabled={busy}>
          Registrar
        </button>
      }
    >
      <p className="muted small">
        Ao contratar um plano o pagamento do aluno já é criado como pendente. Use este formulário para pagamentos de
        professores ou para planos sem pagamento ativo.
      </p>
      <form id="payment-form" onSubmit={submit}>
        <div className="segmented" role="group" aria-label="Tipo de pagamento">
          {(["student", "teacher"] as Kind[]).map((k) => (
            <button key={k} type="button" className={`seg ${kind === k ? "seg-present is-on" : ""}`} onClick={() => setKind(k)}>
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>

        {kind === "student" ? (
          <div className="form-row">
            <label className="field">
              <span>Aluno</span>
              <select
                value={studentId}
                onChange={(e) => {
                  setStudentId(e.target.value ? Number(e.target.value) : "");
                  setSubscriptionId("");
                }}
                required
              >
                <option value="">Selecione…</option>
                {(students.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Plano</span>
              <select
                value={subscriptionId}
                onChange={(e) => setSubscriptionId(e.target.value ? Number(e.target.value) : "")}
                disabled={studentId === ""}
                required
              >
                <option value="">{studentId !== "" && options.length === 0 ? "Nenhum plano disponível" : "Selecione…"}</option>
                {options.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.plan_name} · {money(s.final_price)} · desde {fmtDate(s.start_date)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : (
          <>
            <div className="form-row">
              <label className="field">
                <span>Professor</span>
                <select value={teacherId} onChange={(e) => setTeacherId(e.target.value ? Number(e.target.value) : "")} required>
                  <option value="">Selecione…</option>
                  {(teachers.data ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Valor (R$)</span>
                <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
              </label>
            </div>
            <div className="form-row">
              <label className="field">
                <span>Período — de</span>
                <DateInput value={periodStart} onChange={setPeriodStart} aria-label="Início do período" />
              </label>
              <label className="field">
                <span>Período — até</span>
                <DateInput value={periodEnd} onChange={setPeriodEnd} aria-label="Fim do período" />
              </label>
            </div>
            <p className="muted small">O valor devido a cada professor no período está em Professores e no Caixa.</p>
          </>
        )}

        <div className="field">
          <span>Pagamento</span>
          <div className="paid-row">
            <label className="check">
              <input type="checkbox" checked={isPaid} onChange={(e) => setIsPaid(e.target.checked)} />
              <span>Já foi pago</span>
            </label>
            {isPaid && <DateInput value={paidAt} onChange={setPaidAt} aria-label="Data do pagamento" />}
          </div>
        </div>
        <label className="field">
          <span>Observações (opcional)</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} rows={3} />
        </label>
      </form>
      {error && <ErrorBox message={error} />}
    </Modal>
  );
}
