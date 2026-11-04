import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { api, call } from "../lib/api";
import { DateInput } from "./DateInput";
import { addDays, fmtDate, fmtHour, money, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";
import { ConfirmPanel } from "./ConfirmPanel";
import { Modal } from "./Modal";
import { ServiceSessionPanel, sessionStatus } from "./ServiceSessionPanel";
import { Badge, ErrorBox, Loading } from "./ui";

type Contract = Schemas["ServiceContractRead"];
type Recurrence = Contract["recurrence"];

const recurrenceLabel: Record<Recurrence, string> = {
  none: "Sem recorrência",
  weekly: "Semanal",
  biweekly: "Quinzenal",
  monthly: "Mensal",
};
const situation: Record<string, [string, string]> = {
  active: ["Em andamento", "success"],
  completed: ["Concluído", "neutral"],
  cancelled: ["Cancelado", "danger"],
};
const sessionIcon: Record<string, string> = { scheduled: "", done: "✓ ", missed: "✗ ", cancelled: "⊘ " };

/** Mesma regra do back para pré-visualizar as datas das sessões. */
function previewDates(start: string, recurrence: Recurrence, n: number): string[] {
  if (recurrence === "none") return [start];
  const d0 = parseISO(start);
  return Array.from({ length: n }, (_, i) => {
    if (recurrence === "monthly") {
      const target = new Date(d0.getFullYear(), d0.getMonth() + i, 1);
      const last = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
      return toISO(new Date(target.getFullYear(), target.getMonth(), Math.min(d0.getDate(), last)));
    }
    return toISO(addDays(d0, (recurrence === "weekly" ? 7 : 14) * i));
  });
}

export function StudentServices({ studentId, active, version, onChanged }: {
  studentId: number;
  active: boolean;
  version: number;
  onChanged: () => void;
}) {
  const { isAdmin } = useSession();
  const contracts = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}/services", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );
  const [contracting, setContracting] = useState(false);
  const [openSession, setOpenSession] = useState<number | null>(null);
  const [error, setError] = useState<string>();

  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      contracts.reload();
      onChanged();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  const path = (c: Contract) => ({ student_id: studentId, contract_id: c.id });

  return (
    <div className="card">
      <div className="card-title-row">
        <h3 className="card-title">Serviços avulsos</h3>
        {isAdmin && active && (
          <button className="btn btn-sm" onClick={() => setContracting(true)}>
            + Contratar serviço
          </button>
        )}
      </div>
      {contracts.loading && !contracts.data && <Loading />}
      {(contracts.error || error) && <ErrorBox message={(contracts.error || error)!} />}
      {contracts.data?.length === 0 && <p className="muted">Nenhum serviço avulso contratado.</p>}

      <ul className="service-contracts">
        {(contracts.data ?? []).map((c) => {
          const [label, tone] = situation[c.situation];
          return (
            <li key={c.id} className={`service-contract is-${c.situation}`}>
              <div className="sc-head">
                <div>
                  <strong>{c.service_name}</strong>{" "}
                  <span className="muted small">
                    · {recurrenceLabel[c.recurrence]}
                    {c.occurrences > 1 && ` · ${c.occurrences} sessões`} · contratado em {fmtDate(c.created_at.slice(0, 10))}
                  </span>
                </div>
                <Badge tone={tone}>{label}</Badge>
              </div>

              <div className="sc-values">
                <span>
                  {money(c.price)}/sessão
                  {c.price_changed && <span className="muted small strike"> {money(c.list_price)}</span>}
                </span>
                {c.occurrences > 1 && <span className="muted small">Total {money(c.total_price)}</span>}
                <span className="muted small">
                  {c.done_count}/{c.occurrences} realizada(s)
                  {c.next_date && <> · próxima {fmtDate(c.next_date)}</>}
                </span>
                {isAdmin ? (
                  <label className="check small sc-paid">
                    <input
                      type="checkbox"
                      checked={c.is_paid}
                      onChange={(e) =>
                        run(() =>
                          call(
                            api.PATCH("/api/v1/students/{student_id}/services/{contract_id}", {
                              params: { path: path(c) },
                              body: { is_paid: e.target.checked },
                            }),
                          ),
                        )
                      }
                    />
                    <span>{c.is_paid ? `Pago${c.paid_at ? ` em ${fmtDate(c.paid_at)}` : ""}` : "Pagamento pendente"}</span>
                  </label>
                ) : (
                  <Badge tone={c.is_paid ? "success" : "warning"}>{c.is_paid ? "Pago" : "Pendente"}</Badge>
                )}
              </div>

              {c.start_hour != null && (
                <p className="muted small">
                  {fmtHour(c.start_hour)} · {c.room?.name ?? "—"} · {c.teacher?.name ?? "—"}
                </p>
              )}
              <ul className="sc-sessions">
                {c.sessions.map((s) => (
                  <li key={s.id}>
                    <button
                      className={`session-chip is-${s.status} ${s.status === "scheduled" && s.date <= todayISO() ? "is-due" : ""}`}
                      title={`${sessionStatus[s.status][0]}${s.justification ? ` — “${s.justification}”` : ""} · clique para detalhes`}
                      onClick={() => setOpenSession(s.id)}
                    >
                      {sessionIcon[s.status]}
                      {fmtDate(s.date)}
                    </button>
                  </li>
                ))}
              </ul>

              <ContractNotes
                contract={c}
                canEdit={isAdmin}
                onSave={(notes) =>
                  run(() =>
                    call(
                      api.PATCH("/api/v1/students/{student_id}/services/{contract_id}", {
                        params: { path: path(c) },
                        body: { notes: notes || null },
                      }),
                    ),
                  )
                }
              />

              {isAdmin && c.situation === "active" && confirmCancelId !== c.id && (
                <div className="sc-actions">
                  <button className="btn btn-sm btn-danger-outline" onClick={() => setConfirmCancelId(c.id)}>
                    Cancelar serviço
                  </button>
                </div>
              )}
              {isAdmin && c.situation === "active" && confirmCancelId === c.id && (() => {
                const today = todayISO();
                const future = c.sessions.filter((s) => s.status === "scheduled" && s.date >= today).length;
                return (
                  <ConfirmPanel
                    title={`Cancelar ${c.service_name}`}
                    confirmLabel="Cancelar serviço"
                    tone="danger"
                    onConfirm={async () => {
                      const ok = await run(() =>
                        call(
                          api.POST("/api/v1/students/{student_id}/services/{contract_id}/cancel", {
                            params: { path: path(c) },
                          }),
                        ),
                      );
                      if (ok) setConfirmCancelId(null);
                    }}
                    onCancel={() => setConfirmCancelId(null)}
                  >
                    <p>
                      {future > 0
                        ? `${future} sessão(ões) agendada(s) de hoje em diante serão canceladas e liberam a sala e o profissional.`
                        : "Não há sessões agendadas daqui para frente."}
                    </p>
                    <p className="muted small">Sessões já finalizadas continuam no histórico e no pagamento do profissional.</p>
                  </ConfirmPanel>
                );
              })()}
            </li>
          );
        })}
      </ul>

      {openSession != null && (
        <ServiceSessionPanel
          sessionId={openSession}
          onClose={() => setOpenSession(null)}
          onChanged={() => {
            contracts.reload();
            onChanged();
          }}
        />
      )}
      {contracting && (
        <ContractModal
          studentId={studentId}
          onClose={() => setContracting(false)}
          onSaved={() => {
            setContracting(false);
            contracts.reload();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function ContractNotes({ contract, canEdit, onSave }: { contract: Contract; canEdit: boolean; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(contract.notes ?? "");
  if (editing) {
    return (
      <div className="sc-notes-edit">
        <textarea rows={2} value={value} onChange={(e) => setValue(e.target.value)} placeholder="Observações sobre o serviço" />
        <div className="form-actions">
          <button className="btn btn-sm btn-ghost" onClick={() => setEditing(false)}>
            Cancelar
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => {
              onSave(value);
              setEditing(false);
            }}
          >
            Salvar
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="sc-notes">
      {contract.notes ? <span>📝 {contract.notes}</span> : <span className="muted small">Sem observações</span>}
      {canEdit && (
        <button className="link-button small" onClick={() => setEditing(true)}>
          {contract.notes ? "editar" : "adicionar observação"}
        </button>
      )}
    </div>
  );
}

function ContractModal({ studentId, onClose, onSaved }: { studentId: number; onClose: () => void; onSaved: () => void }) {
  const { session } = useSession();
  const services = useAsync(() => call(api.GET("/api/v1/services")), []);
  const rooms = useAsync(() => call(api.GET("/api/v1/rooms")), []);
  const teachers = useAsync(() => call(api.GET("/api/v1/teachers")), []);
  const [serviceId, setServiceId] = useState<number | "">("");
  const [roomId, setRoomId] = useState<number | "">("");
  const [teacherId, setTeacherId] = useState<number | "">("");
  const openHour = session?.studio.open_hour ?? 6;
  const closeHour = session?.studio.close_hour ?? 19;
  const [startHour, setStartHour] = useState(Math.max(openHour, 9));
  const [price, setPrice] = useState("");
  const [recurrence, setRecurrence] = useState<Recurrence>("none");
  const [occurrences, setOccurrences] = useState(4);
  const [startDate, setStartDate] = useState(todayISO());
  const [isPaid, setIsPaid] = useState(false);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const service = services.data?.find((s) => s.id === serviceId);
  const n = recurrence === "none" ? 1 : occurrences;
  const dates = previewDates(startDate, recurrence, n);
  const changed = service && price !== "" && Number(price) !== Number(service.price);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (serviceId === "" || roomId === "" || teacherId === "") return setError("Selecione serviço, sala e profissional");
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.POST("/api/v1/students/{student_id}/services", {
          params: { path: { student_id: studentId } },
          body: {
            service_id: serviceId,
            room_id: roomId,
            teacher_id: teacherId,
            start_hour: startHour,
            price: price === "" ? null : price,
            recurrence,
            occurrences: recurrence === "none" ? null : occurrences,
            start_date: startDate,
            is_paid: isPaid,
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
      title="Contratar serviço avulso"
      onClose={onClose}
      footer={
        <button
          type="submit"
          form="contract-form"
          className="btn btn-primary"
          disabled={busy || serviceId === "" || roomId === "" || teacherId === ""}
        >
          Contratar
        </button>
      }
    >
      {services.loading && !services.data && <Loading />}
      <form id="contract-form" onSubmit={submit}>
        <div className="form-row">
          <label className="field">
            <span>Serviço</span>
            <select
              value={serviceId}
              onChange={(e) => {
                const id = e.target.value ? Number(e.target.value) : "";
                setServiceId(id);
                setPrice(services.data?.find((s) => s.id === id)?.price ?? "");
              }}
              required
            >
              <option value="">Selecione…</option>
              {(services.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {money(s.price)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Valor por sessão {changed && <span className="text-warning">(tabela {money(service!.price)})</span>}</span>
            <div className="input-money">
              <span>R$</span>
              <input
                type="number"
                min={0}
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                disabled={serviceId === ""}
              />
            </div>
          </label>
        </div>
        <div className="form-row form-row-3">
          <label className="field">
            <span>Profissional</span>
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
            <span>Sala</span>
            <select value={roomId} onChange={(e) => setRoomId(e.target.value ? Number(e.target.value) : "")} required>
              <option value="">Selecione…</option>
              {(rooms.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Horário (1h)</span>
            <select value={startHour} onChange={(e) => setStartHour(Number(e.target.value))}>
              {Array.from({ length: closeHour - openHour }, (_, i) => openHour + i).map((h) => (
                <option key={h} value={h}>
                  {fmtHour(h)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>Recorrência</span>
            <select value={recurrence} onChange={(e) => setRecurrence(e.target.value as Recurrence)}>
              {(Object.keys(recurrenceLabel) as Recurrence[]).map((r) => (
                <option key={r} value={r}>
                  {recurrenceLabel[r]}
                </option>
              ))}
            </select>
          </label>
          {recurrence !== "none" ? (
            <label className="field">
              <span>Número de sessões</span>
              <input type="number" min={2} max={52} value={occurrences} onChange={(e) => setOccurrences(Number(e.target.value))} />
            </label>
          ) : (
            <div />
          )}
        </div>
        <div className="form-row">
          <label className="field">
            <span>{recurrence === "none" ? "Data da sessão" : "Primeira sessão"}</span>
            <DateInput value={startDate} onChange={setStartDate} required />
          </label>
          <div className="field">
            <span>Pagamento</span>
            <label className="check">
              <input type="checkbox" checked={isPaid} onChange={(e) => setIsPaid(e.target.checked)} />
              <span>Já foi pago</span>
            </label>
          </div>
        </div>
        <label className="field">
          <span>Observações</span>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Ex.: indicação médica, foco do tratamento…" />
        </label>
      </form>

      {service && (
        <div className="pay-examples">
          <span className="field-label">Resumo</span>
          <ul>
            <li>
              <span>Sessões</span>
              <span className="small">{dates.map(fmtDate).join(" · ")}</span>
            </li>
            <li>
              <span>Total</span>
              <strong>{money(Number(price || 0) * n)}</strong>
            </li>
          </ul>
        </div>
      )}
      {error && <ErrorBox message={error} />}
    </Modal>
  );
}
