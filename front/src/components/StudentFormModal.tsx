import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { api, call } from "../lib/api";
import { fmtDate, money, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { subscriptionUsage } from "../lib/labels";
import { GroupPicker } from "./GroupPicker";
import { Modal } from "./Modal";
import { ErrorBox, Loading } from "./ui";

type Detail = Schemas["StudentDetail"];
type Sub = Schemas["SubscriptionRead"];

type Props = {
  /** Sem aluno = cadastro; com aluno = edição. */
  student?: Detail;
  onClose: () => void;
  onSaved: (studentId: number) => void;
};

function ListInput({ label, values, onChange, type, placeholder }: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  type: string;
  placeholder: string;
}) {
  const items = values.length ? values : [""];
  return (
    <div className="field">
      <span>{label}</span>
      {items.map((v, i) => (
        <div key={i} className="list-input">
          <input
            type={type}
            value={v}
            placeholder={placeholder}
            onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))}
          />
          {items.length > 1 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(items.filter((_, j) => j !== i))}>
              ✕
            </button>
          )}
        </div>
      ))}
      {items.length < 5 && (
        <button type="button" className="btn btn-ghost btn-sm add-more" onClick={() => onChange([...items, ""])}>
          + adicionar
        </button>
      )}
    </div>
  );
}

export function StudentFormModal({ student, onClose, onSaved }: Props) {
  const editing = !!student;
  const plans = useAsync(() => call(api.GET("/api/v1/plans")), []);
  const groups = useAsync(() => call(api.GET("/api/v1/class-groups")), []);

  // Dados pessoais
  const [name, setName] = useState(student?.name ?? "");
  const [phones, setPhones] = useState<string[]>(student?.phones ?? []);
  const [emails, setEmails] = useState<string[]>(student?.emails ?? []);
  const [birthDate, setBirthDate] = useState(student?.birth_date ?? "");
  const [notes, setNotes] = useState(student?.notes ?? "");

  // Plano (cadastro)
  const [planId, setPlanId] = useState<number | "">("");
  const [discountId, setDiscountId] = useState<number | "">("");
  const [startDate, setStartDate] = useState(todayISO());
  const [isPaid, setIsPaid] = useState(false);
  const [paidAt, setPaidAt] = useState(todayISO());

  // Plano (edição): pagamento dos planos em uso/aguardando
  const editableSubs: Sub[] = student
    ? [...(student.subscription && student.subscription.usage !== "cancelled" ? [student.subscription] : []), ...student.queued_subscriptions]
    : [];
  const [payments, setPayments] = useState<Record<number, { is_paid: boolean; paid_at: string }>>(() =>
    Object.fromEntries(editableSubs.map((s) => [s.id, { is_paid: s.is_paid, paid_at: s.paid_at ?? todayISO() }])),
  );

  // Turmas padrão
  const ownGroupIds = student?.schedule.map((g) => g.class_group_id) ?? [];
  const [groupIds, setGroupIds] = useState<number[]>(ownGroupIds);
  const [effectiveFrom, setEffectiveFrom] = useState(todayISO());

  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const discounts = useAsync(
    () => (planId === "" ? Promise.resolve([]) : call(api.GET("/api/v1/discounts", { params: { query: { plan_id: planId } } }))),
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

  const plan = plans.data?.find((p) => p.id === planId);
  const limit = editing
    ? Math.max(0, ...editableSubs.map((s) => s.sessions_per_week))
    : (plan?.sessions_per_week ?? 0);
  const scheduleChanged =
    editing && (groupIds.length !== ownGroupIds.length || groupIds.some((id) => !ownGroupIds.includes(id)));
  const clean = (list: string[]) => list.map((v) => v.trim()).filter(Boolean);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (!editing) {
        const created = await call(
          api.POST("/api/v1/students", {
            body: {
              name,
              phones: clean(phones),
              emails: clean(emails),
              birth_date: birthDate || null,
              notes: notes || null,
              subscription:
                planId === ""
                  ? null
                  : {
                      plan_id: planId,
                      discount_id: discountId === "" ? null : discountId,
                      start_date: startDate,
                      is_paid: isPaid,
                      paid_at: isPaid ? paidAt : null,
                    },
              class_group_ids: planId === "" ? [] : groupIds,
            },
          }),
        );
        onSaved(created.id);
        return;
      }

      const sid = student!.id;
      await call(
        api.PATCH("/api/v1/students/{student_id}", {
          params: { path: { student_id: sid } },
          body: { name, phones: clean(phones), emails: clean(emails), birth_date: birthDate || null, notes: notes || null },
        }),
      );
      for (const s of editableSubs) {
        const p = payments[s.id];
        if (p.is_paid !== s.is_paid || (p.is_paid && p.paid_at !== s.paid_at)) {
          await call(
            api.PATCH("/api/v1/students/{student_id}/subscriptions/{subscription_id}/payment", {
              params: { path: { student_id: sid, subscription_id: s.id } },
              body: { is_paid: p.is_paid, paid_at: p.is_paid ? p.paid_at : null },
            }),
          );
        }
      }
      if (scheduleChanged) {
        await call(
          api.PUT("/api/v1/students/{student_id}/schedule", {
            params: { path: { student_id: sid } },
            body: { class_group_ids: groupIds, effective_from: effectiveFrom },
          }),
        );
      }
      onSaved(sid);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={editing ? `Editar ${student!.name}` : "Novo aluno"}
      subtitle={editing ? "As alterações ficam registradas no histórico do aluno." : undefined}
      onClose={onClose}
      wide
      footer={
        <button type="submit" form="student-form" className="btn btn-primary" disabled={busy || !name.trim()}>
          {busy ? "Salvando…" : editing ? "Salvar alterações" : "Cadastrar aluno"}
        </button>
      }
    >
      <form id="student-form" onSubmit={submit} className="student-form">
        <section>
          <h3 className="section-title">Dados</h3>
          <div className="form-row">
            <label className="field">
              <span>Nome</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
            </label>
            <label className="field">
              <span>Data de nascimento</span>
              <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
            </label>
          </div>
          <div className="form-row">
            <ListInput label="Telefones" values={phones} onChange={setPhones} type="tel" placeholder="11 99999-0000" />
            <ListInput label="E-mails" values={emails} onChange={setEmails} type="email" placeholder="nome@email.com" />
          </div>
          <label className="field">
            <span>Observações</span>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Restrições, lesões, preferências…" />
          </label>
        </section>

        <section>
          <h3 className="section-title">Plano</h3>
          {!editing ? (
            <>
              {plans.loading && !plans.data && <Loading />}
              <div className="form-row">
                <label className="field">
                  <span>Plano</span>
                  <select
                    value={planId}
                    onChange={(e) => {
                      setPlanId(e.target.value ? Number(e.target.value) : "");
                      setDiscountId("");
                      setGroupIds([]);
                    }}
                  >
                    <option value="">Sem plano por enquanto</option>
                    {(plans.data ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} · {p.sessions_per_week}x/semana · {p.total_classes} aulas · {money(p.price)}
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
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {planId !== "" && (
                <div className="form-row">
                  <label className="field">
                    <span>Data da contratação</span>
                    <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                  </label>
                  <div className="field">
                    <span>Pagamento {price.data && <>· {money(price.data.final_price)}</>}</span>
                    <div className="paid-row">
                      <label className="check">
                        <input type="checkbox" checked={isPaid} onChange={(e) => setIsPaid(e.target.checked)} />
                        <span>Já foi pago</span>
                      </label>
                      {isPaid && <input type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} aria-label="Data do pagamento" />}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : editableSubs.length === 0 ? (
            <p className="muted small">Sem plano ativo. Use “Renovar plano” na ficha para contratar um.</p>
          ) : (
            <ul className="stack-sm">
              {editableSubs.map((s) => {
                const p = payments[s.id];
                return (
                  <li key={s.id} className="sub-pay">
                    <div>
                      <strong>{s.plan_name ?? s.plan.name}</strong>{" "}
                      <span className="muted small">
                        · {subscriptionUsage[s.usage]} · {money(s.final_price)} · contratado em {fmtDate(s.start_date)}
                      </span>
                    </div>
                    <div className="paid-row">
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={p.is_paid}
                          onChange={(e) => setPayments({ ...payments, [s.id]: { ...p, is_paid: e.target.checked } })}
                        />
                        <span>Pago</span>
                      </label>
                      {p.is_paid && (
                        <input
                          type="date"
                          value={p.paid_at}
                          onChange={(e) => setPayments({ ...payments, [s.id]: { ...p, paid_at: e.target.value } })}
                          aria-label="Data do pagamento"
                        />
                      )}
                    </div>
                  </li>
                );
              })}
              <li className="muted small">Para trocar ou renovar o plano, use “Renovar plano” na ficha.</li>
            </ul>
          )}
        </section>

        <section>
          <div className="card-title-row">
            <h3 className="section-title">
              Turmas padrão{" "}
              <span className="muted small">
                {limit > 0 ? `(${groupIds.length} de ${limit} pelo plano)` : "(escolha um plano primeiro)"}
              </span>
            </h3>
            {editing && scheduleChanged && (
              <label className="field inline-field">
                <span>Vale a partir de</span>
                <input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
              </label>
            )}
          </div>
          {groups.loading && !groups.data && <Loading />}
          {limit > 0 && groups.data && (
            <GroupPicker groups={groups.data} selected={groupIds} ownGroupIds={ownGroupIds} limit={limit} onChange={setGroupIds} />
          )}
          {editing && scheduleChanged && (
            <p className="muted small">
              O horário anterior vale até a véspera de {fmtDate(effectiveFrom)} e fica no histórico de horários; aulas já
              feitas não mudam.
            </p>
          )}
        </section>
      </form>
      {error && <ErrorBox message={error} />}
    </Modal>
  );
}
