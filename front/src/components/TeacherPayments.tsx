import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { api, call } from "../lib/api";
import { fmtDate, money, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { DateInput } from "./DateInput";
import { Modal } from "./Modal";
import { PaymentActionModal, type PaymentAction } from "./PaymentActionModal";
import { Badge, Empty, ErrorBox, Loading } from "./ui";

type Payment = Schemas["PaymentRead"];

const STATUS_LABEL: Record<Payment["status"], string> = { pending: "Pendente", paid: "Pago", cancelled: "Cancelado" };
const STATUS_TONE: Record<Payment["status"], string> = { pending: "warning", paid: "success", cancelled: "danger" };

type Props = {
  teacher: Schemas["TeacherSummary"];
  /** Valor devido no mês exibido (aulas + serviços finalizados): sugestão para o novo pagamento. */
  owed: string;
  periodStart: string;
  periodEnd: string;
};

/** Pagamentos feitos ao professor: data, valor e status. Ficam na ficha do professor. */
export function TeacherPayments({ teacher, owed, periodStart, periodEnd }: Props) {
  const list = useAsync(
    () => call(api.GET("/api/v1/payments", { params: { query: { kind: "teacher", teacher_id: teacher.id, limit: 500 } } })),
    [teacher.id],
  );
  const [creating, setCreating] = useState(false);
  const [action, setAction] = useState<PaymentAction>();
  const done = () => {
    setCreating(false);
    setAction(undefined);
    list.reload();
  };
  const data = list.data;

  return (
    <div className="teacher-payments">
      <div className="card-title-row">
        <h4 className="card-title">Pagamentos ao professor</h4>
        <button className="btn btn-sm btn-primary" onClick={() => setCreating(true)}>
          Registrar pagamento
        </button>
      </div>
      {list.loading && !data && <Loading />}
      {list.error && <ErrorBox message={list.error} />}
      {data && (
        <>
          <p className="muted small">
            Pago {money(data.totals.paid)} · Pendente {money(data.totals.pending)}. O que foi pago entra como desconto no Caixa.
          </p>
          {data.items.length === 0 ? (
            <Empty>Nenhum pagamento registrado para este professor.</Empty>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Período</th>
                    <th className="num">Valor</th>
                    <th>Status</th>
                    <th>Observações</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        {fmtDate(p.paid_at ?? p.created_at)}
                        <div className="muted small">{p.paid_at ? "pagamento" : "criado em"}</div>
                      </td>
                      <td className="small">
                        {p.period_start && p.period_end ? `${fmtDate(p.period_start)} a ${fmtDate(p.period_end)}` : "—"}
                      </td>
                      <td className="num">
                        <strong>{money(p.amount)}</strong>
                      </td>
                      <td>
                        <Badge tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Badge>
                        {p.cancelled_at && <div className="muted small">em {fmtDate(p.cancelled_at)}</div>}
                      </td>
                      <td className="small">{p.notes || <span className="muted">—</span>}</td>
                      <td>
                        <div className="toolbar">
                          {p.status === "pending" && (
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
        </>
      )}
      {creating && (
        <NewTeacherPayment
          teacher={teacher}
          owed={owed}
          periodStart={periodStart}
          periodEnd={periodEnd}
          onClose={() => setCreating(false)}
          onDone={done}
        />
      )}
      {action && <PaymentActionModal action={action} onClose={() => setAction(undefined)} onDone={done} />}
    </div>
  );
}

function NewTeacherPayment({ teacher, owed, periodStart, periodEnd, onClose, onDone }: Props & { onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(Number(owed) > 0 ? Number(owed).toFixed(2) : "");
  const [start, setStart] = useState(periodStart);
  const [end, setEnd] = useState(periodEnd);
  const [isPaid, setIsPaid] = useState(true);
  const [paidAt, setPaidAt] = useState(todayISO());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.POST("/api/v1/payments", {
          body: {
            kind: "teacher",
            teacher_id: teacher.id,
            amount: amount.replace(",", "."),
            period_start: start || null,
            period_end: end || null,
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
      title="Registrar pagamento"
      subtitle={teacher.name}
      onClose={onClose}
      footer={
        <button type="submit" form="teacher-payment-form" className="btn btn-primary" disabled={busy}>
          Registrar
        </button>
      }
    >
      <form id="teacher-payment-form" onSubmit={submit}>
        <div className="form-row">
          <label className="field">
            <span>Valor pago (R$)</span>
            <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
            <small className="muted">Devido no período exibido: {money(owed)}</small>
          </label>
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
        </div>
        <div className="form-row">
          <label className="field">
            <span>Período — de</span>
            <DateInput value={start} onChange={setStart} aria-label="Início do período" />
          </label>
          <label className="field">
            <span>Período — até</span>
            <DateInput value={end} onChange={setEnd} aria-label="Fim do período" />
          </label>
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
