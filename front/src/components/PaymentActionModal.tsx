import type { Schemas } from "@pilates/api-client";
import { useState } from "react";

import { api, call } from "../lib/api";
import { money, todayISO } from "../lib/format";
import { ConfirmPanel } from "./ConfirmPanel";
import { DateInput } from "./DateInput";
import { Modal } from "./Modal";
import { ErrorBox } from "./ui";

type Payment = Schemas["PaymentRead"];
export type PaymentAction = { payment: Payment; type: "pay" | "pending" | "cancel" | "notes" };

function describe(p: Payment) {
  return `${p.student?.name ?? p.teacher?.name ?? ""} · ${money(p.amount)}`;
}

export function PaymentActionModal({ action, onClose, onDone }: { action: PaymentAction; onClose: () => void; onDone: () => void }) {
  const { payment, type } = action;
  const [paidAt, setPaidAt] = useState(todayISO());
  const [notes, setNotes] = useState(type === "notes" ? payment.notes ?? "" : "");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const path = { payment_id: payment.id };

  async function run() {
    setBusy(true);
    setError(undefined);
    try {
      if (type === "pay") await call(api.POST("/api/v1/payments/{payment_id}/pay", { params: { path }, body: { paid_at: paidAt } }));
      else if (type === "pending") await call(api.POST("/api/v1/payments/{payment_id}/pending", { params: { path } }));
      else if (type === "cancel")
        await call(api.POST("/api/v1/payments/{payment_id}/cancel", { params: { path }, body: { notes: notes || null } }));
      else await call(api.PATCH("/api/v1/payments/{payment_id}", { params: { path }, body: { notes: notes || null } }));
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  if (type === "notes") {
    return (
      <Modal
        title="Observações"
        subtitle={describe(payment)}
        onClose={onClose}
        footer={
          <button className="btn btn-primary" disabled={busy} onClick={run}>
            Salvar
          </button>
        }
      >
        <label className="field">
          <span>Observações</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} rows={4} />
        </label>
        {error && <ErrorBox message={error} />}
      </Modal>
    );
  }

  const copy = {
    pay: { title: "Marcar como pago", label: "Confirmar pagamento", tone: "warning" as const },
    pending: { title: "Voltar para pendente", label: "Voltar a pendente", tone: "warning" as const },
    cancel: { title: "Cancelar pagamento", label: "Cancelar pagamento", tone: "danger" as const },
  }[type];

  return (
    <Modal title={copy.title} subtitle={describe(payment)} onClose={onClose}>
      <ConfirmPanel title={copy.title} confirmLabel={copy.label} tone={copy.tone} busy={busy} onConfirm={run} onCancel={onClose}>
        {type === "pay" && (
          <label className="field">
            <span>Data do pagamento</span>
            <DateInput value={paidAt} onChange={setPaidAt} aria-label="Data do pagamento" />
          </label>
        )}
        {type === "pending" && <p>A data de pagamento será removida e o plano do aluno volta a constar como pendente.</p>}
        {type === "cancel" && (
          <label className="field">
            <span>Motivo (opcional)</span>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} />
          </label>
        )}
        {error && <ErrorBox message={error} />}
      </ConfirmPanel>
    </Modal>
  );
}
