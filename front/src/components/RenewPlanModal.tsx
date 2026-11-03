import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { api, call } from "../lib/api";
import { money, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { Modal } from "./Modal";
import { ErrorBox, Loading } from "./ui";

type Props = { student: Schemas["StudentDetail"]; onClose: () => void; onSaved: () => void };

export function RenewPlanModal({ student, onClose, onSaved }: Props) {
  const plans = useAsync(() => call(api.GET("/api/v1/plans")), []);
  const current = student.subscription;
  const [planId, setPlanId] = useState<number | "">(current?.plan.id ?? "");
  const [discountId, setDiscountId] = useState<number | "">("");
  const [startDate, setStartDate] = useState(todayISO());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const discounts = useAsync(
    () =>
      planId === ""
        ? Promise.resolve([])
        : call(api.GET("/api/v1/discounts", { params: { query: { plan_id: planId } } })),
    [planId],
  );
  const price = useAsync(
    () =>
      planId === ""
        ? Promise.resolve(null)
        : call(
            api.GET("/api/v1/plans/{plan_id}/price", {
              params: { path: { plan_id: planId }, query: { discount_id: discountId === "" ? undefined : discountId } },
            }),
          ),
    [planId, discountId],
  );

  const early = current && current.usage === "in_use" && current.credits_remaining > 0;
  const plan = plans.data?.find((p) => p.id === planId);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (planId === "") return setError("Selecione o plano");
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.POST("/api/v1/students/{student_id}/subscriptions", {
          params: { path: { student_id: student.id } },
          body: {
            plan_id: planId,
            discount_id: discountId === "" ? null : discountId,
            start_date: startDate,
            notes: notes || null,
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

  return (
    <Modal
      title="Renovar plano"
      subtitle={student.name}
      onClose={onClose}
      footer={
        <button type="submit" form="renew-form" className="btn btn-primary" disabled={busy || planId === ""}>
          Confirmar renovação
        </button>
      }
    >
      {early && (
        <div className="alert alert-info">
          O plano em uso ainda tem <strong>{current.credits_remaining} aula(s)</strong>. Ele continua sendo contado até
          o fim; o novo plano começa a contar depois.
        </div>
      )}
      {plans.loading && !plans.data && <Loading />}
      <form id="renew-form" onSubmit={submit}>
        <div className="form-row">
          <label className="field">
            <span>Plano</span>
            <select
              value={planId}
              onChange={(e) => {
                setPlanId(e.target.value ? Number(e.target.value) : "");
                setDiscountId("");
              }}
              required
            >
              <option value="">Selecione…</option>
              {(plans.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.total_classes} aulas · {money(p.price)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Desconto</span>
            <select
              value={discountId}
              onChange={(e) => setDiscountId(e.target.value ? Number(e.target.value) : "")}
              disabled={planId === ""}
            >
              <option value="">Sem desconto</option>
              {(discounts.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.kind === "percent" ? `${Number(d.value)}%` : money(d.value)})
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>Data da contratação</span>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label className="field">
            <span>Observação (opcional)</span>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
          </label>
        </div>
      </form>

      {price.data && plan && (
        <div className="pay-examples">
          <span className="field-label">Valores que ficarão congelados</span>
          <ul>
            <li>
              <span>Preço do plano</span>
              <span>{money(price.data.base_price)}</span>
            </li>
            {Number(price.data.discount_amount) > 0 && (
              <li>
                <span>Desconto</span>
                <span>− {money(price.data.discount_amount)}</span>
              </li>
            )}
            <li>
              <span>Valor a pagar</span>
              <strong>{money(price.data.final_price)}</strong>
            </li>
            <li>
              <span>Por aula ({plan.total_classes} aulas)</span>
              <span>{money(Number(price.data.final_price) / plan.total_classes)}</span>
            </li>
          </ul>
        </div>
      )}
      {error && <ErrorBox message={error} />}
    </Modal>
  );
}
