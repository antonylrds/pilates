import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { perWeekLabel } from "../lib/labels";
import { money } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";
import { ServicesTab } from "./ServicesPage";

type Plan = Schemas["PlanRead"];
type Discount = Schemas["DiscountRead"];
type Overview = Schemas["CatalogOverview"];

const TABS = [
  { id: "planos", label: "Planos" },
  { id: "descontos", label: "Descontos" },
  { id: "servicos", label: "Serviços avulsos" },
] as const;

// A API lista só ativos por padrão (e o cliente omite parâmetros nulos): inativos vêm numa segunda busca.
const fetchPlans = async (withInactive: boolean): Promise<Plan[]> => {
  const active = await call(api.GET("/api/v1/plans", { params: { query: { is_active: true } } }));
  if (!withInactive) return active;
  return [...active, ...(await call(api.GET("/api/v1/plans", { params: { query: { is_active: false } } })))];
};
const fetchDiscounts = async (withInactive: boolean): Promise<Discount[]> => {
  const active = await call(api.GET("/api/v1/discounts", { params: { query: { is_active: true } } }));
  if (!withInactive) return active;
  return [...active, ...(await call(api.GET("/api/v1/discounts", { params: { query: { is_active: false } } })))];
};

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("aba") ?? "planos";
  const overview = useAsync(() => call(api.GET("/api/v1/catalog/overview")), [tab]);

  return (
    <div className="page page-narrow">
      <header className="page-header">
        <div>
          <h1>Planos e serviços</h1>
          <p className="muted">
            O que o estúdio oferece. Alterações valem para novas contratações; o que já foi contratado mantém os valores
            da época.
          </p>
        </div>
      </header>

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? "is-active" : ""}`}
            onClick={() => setParams({ aba: t.id })}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "planos" && <PlansTab overview={overview.data} onChanged={overview.reload} />}
      {tab === "descontos" && <DiscountsTab />}
      {tab === "servicos" && <ServicesTab overview={overview.data} onChanged={overview.reload} />}
    </div>
  );
}

// ---------- Planos ----------
function PlansTab({ overview, onChanged }: { overview?: Overview; onChanged: () => void }) {
  const { isAdmin } = useSession();
  const [showInactive, setShowInactive] = useState(false);
  const plans = useAsync(() => fetchPlans(showInactive), [showInactive]);
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const usage = (id: number) => overview?.plans.find((p) => p.plan_id === id);
  const reload = () => {
    plans.reload();
    onChanged();
  };

  return (
    <>
      <div className="tab-toolbar">
        <label className="check small">
          <input type="checkbox" checked={showInactive} onChange={() => setShowInactive((v) => !v)} />
          <span>Mostrar inativos</span>
        </label>
        {isAdmin && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            + Novo plano
          </button>
        )}
      </div>

      {editing === "new" && <PlanForm onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
      {plans.loading && !plans.data && <Loading />}
      {plans.error && <ErrorBox message={plans.error} />}
      {plans.data?.length === 0 && <Empty>Nenhum plano cadastrado.</Empty>}

      <ul className="stack">
        {(plans.data ?? []).map((p) => {
          if (editing !== "new" && editing?.id === p.id) {
            return (
              <li key={p.id}>
                <PlanForm plan={p} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />
              </li>
            );
          }
          const u = usage(p.id);
          return (
            <li key={p.id} className={`card catalog-row ${p.is_active ? "" : "is-inactive"}`}>
              <div className="catalog-main">
                <div>
                  <strong>{p.name}</strong> {!p.is_active && <Badge tone="neutral">Inativo</Badge>}
                </div>
                {p.description && <p className="muted small">{p.description}</p>}
                <p className="small">
                  {perWeekLabel(p.sessions_per_week)} · {p.total_classes} aulas ·{" "}
                  <span className="muted">{Number(p.price) === 0 ? "gratuito" : `${money(Number(p.price) / p.total_classes)} por aula`}</span>
                </p>
                {u && (
                  <div className="usage">
                    <span className="usage-chip">{u.in_use} aluno(s) em uso</span>
                    {u.queued > 0 && <span className="usage-chip">{u.queued} na fila</span>}
                    {u.unpaid > 0 && <span className="usage-chip is-warn">{u.unpaid} pagamento(s) pendente(s)</span>}
                  </div>
                )}
              </div>
              <span className="catalog-price">{money(p.price)}</span>
              {isAdmin && (
                <span className="catalog-actions">
                  <button className="btn btn-sm" onClick={() => setEditing(p)}>
                    Editar
                  </button>
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={async () => {
                      await call(
                        api.PATCH("/api/v1/plans/{plan_id}", {
                          params: { path: { plan_id: p.id } },
                          body: { is_active: !p.is_active },
                        }),
                      );
                      reload();
                    }}
                  >
                    {p.is_active ? "Desativar" : "Reativar"}
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function PlanForm({ plan, onCancel, onSaved }: { plan?: Plan; onCancel: () => void; onSaved: () => void }) {
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [perWeek, setPerWeek] = useState(plan?.sessions_per_week ?? 2);
  const [total, setTotal] = useState(plan?.total_classes ?? 8);
  const [price, setPrice] = useState(plan?.price ?? "");
  const [error, setError] = useState<string>();

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    const body = { name, description: description || null, sessions_per_week: perWeek, total_classes: total, price: price || "0" };
    try {
      if (plan) await call(api.PATCH("/api/v1/plans/{plan_id}", { params: { path: { plan_id: plan.id } }, body }));
      else await call(api.POST("/api/v1/plans", { body }));
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const perLesson = total > 0 && price ? Number(price) / total : 0;

  return (
    <form className="card catalog-form" onSubmit={save}>
      <div className="form-row">
        <label className="field">
          <span>Nome</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Ex.: 2x por semana" />
        </label>
        <label className="field">
          <span>Preço</span>
          <div className="input-money">
            <span>R$</span>
            <input type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} required />
          </div>
        </label>
      </div>
      <div className="form-row">
        <label className="field">
          <span>Aulas por semana</span>
          <select value={perWeek} onChange={(e) => setPerWeek(Number(e.target.value))}>
            {[1, 2, 3, 0].map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "Sem recorrência (só aulas avulsas)" : `${n}x por semana`}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Total de aulas do plano</span>
          <input type="number" min={1} max={500} value={total} onChange={(e) => setTotal(Number(e.target.value))} required />
        </label>
      </div>
      <label className="field">
        <span>Descrição (opcional)</span>
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {perLesson > 0 && (
        <p className="muted small">
          {money(perLesson)} por aula · professor recebe por aluno presente um percentual desse valor (padrão 40% ={" "}
          {money(perLesson * 0.4)}).
        </p>
      )}
      {plan && <p className="muted small">Alterações valem só para novas contratações e renovações.</p>}
      {error && <ErrorBox message={error} />}
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancelar
        </button>
        <button className="btn btn-primary">{plan ? "Salvar" : "Cadastrar"}</button>
      </div>
    </form>
  );
}

// ---------- Descontos ----------
function DiscountsTab() {
  const { isAdmin } = useSession();
  const [showInactive, setShowInactive] = useState(false);
  const discounts = useAsync(() => fetchDiscounts(showInactive), [showInactive]);
  const plans = useAsync(() => fetchPlans(true), []);
  const [editing, setEditing] = useState<Discount | "new" | null>(null);
  const planName = (id: number | null) => (id == null ? "Todos os planos" : (plans.data?.find((p) => p.id === id)?.name ?? "Plano inativo"));
  const done = () => {
    setEditing(null);
    discounts.reload();
  };

  return (
    <>
      <div className="tab-toolbar">
        <label className="check small">
          <input type="checkbox" checked={showInactive} onChange={() => setShowInactive((v) => !v)} />
          <span>Mostrar inativos</span>
        </label>
        {isAdmin && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            + Novo desconto
          </button>
        )}
      </div>
      {editing === "new" && <DiscountForm plans={plans.data ?? []} onCancel={() => setEditing(null)} onSaved={done} />}
      {discounts.loading && !discounts.data && <Loading />}
      {discounts.error && <ErrorBox message={discounts.error} />}
      {discounts.data?.length === 0 && <Empty>Nenhum desconto cadastrado.</Empty>}
      <ul className="stack">
        {(discounts.data ?? []).map((d) =>
          editing !== "new" && editing?.id === d.id ? (
            <li key={d.id}>
              <DiscountForm discount={d} plans={plans.data ?? []} onCancel={() => setEditing(null)} onSaved={done} />
            </li>
          ) : (
            <li key={d.id} className={`card catalog-row ${d.is_active ? "" : "is-inactive"}`}>
              <div className="catalog-main">
                <div>
                  <strong>{d.name}</strong> {!d.is_active && <Badge tone="neutral">Inativo</Badge>}
                </div>
                <p className="muted small">{planName(d.plan_id)}</p>
              </div>
              <span className="catalog-price">{d.kind === "percent" ? `${Number(d.value)}%` : `− ${money(d.value)}`}</span>
              {isAdmin && (
                <span className="catalog-actions">
                  <button className="btn btn-sm" onClick={() => setEditing(d)}>
                    Editar
                  </button>
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={async () => {
                      await call(
                        api.PATCH("/api/v1/discounts/{discount_id}", {
                          params: { path: { discount_id: d.id } },
                          body: { is_active: !d.is_active },
                        }),
                      );
                      discounts.reload();
                    }}
                  >
                    {d.is_active ? "Desativar" : "Reativar"}
                  </button>
                </span>
              )}
            </li>
          ),
        )}
      </ul>
    </>
  );
}

function DiscountForm({ discount, plans, onCancel, onSaved }: {
  discount?: Discount;
  plans: Plan[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(discount?.name ?? "");
  const [kind, setKind] = useState<Discount["kind"]>(discount?.kind ?? "percent");
  const [value, setValue] = useState(discount?.value ?? "");
  const [planId, setPlanId] = useState<number | "">(discount?.plan_id ?? "");
  const [error, setError] = useState<string>();

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    const body = { name, kind, value: value || "0", plan_id: planId === "" ? null : planId };
    try {
      if (discount) {
        await call(api.PATCH("/api/v1/discounts/{discount_id}", { params: { path: { discount_id: discount.id } }, body }));
      } else {
        await call(api.POST("/api/v1/discounts", { body }));
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="card catalog-form" onSubmit={save}>
      <div className="form-row">
        <label className="field">
          <span>Nome</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Ex.: Família" />
        </label>
        <label className="field">
          <span>Vale para</span>
          <select value={planId} onChange={(e) => setPlanId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Todos os planos</option>
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-row">
        <label className="field">
          <span>Tipo</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as Discount["kind"])}>
            <option value="percent">Percentual (%)</option>
            <option value="fixed">Valor fixo (R$)</option>
          </select>
        </label>
        <label className="field">
          <span>Valor</span>
          <div className="input-money">
            <span>{kind === "percent" ? "%" : "R$"}</span>
            <input
              type="number"
              min={0.01}
              max={kind === "percent" ? 100 : undefined}
              step="0.01"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            />
          </div>
        </label>
      </div>
      {discount && <p className="muted small">Alterações não mudam o desconto já aplicado em planos contratados.</p>}
      {error && <ErrorBox message={error} />}
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancelar
        </button>
        <button className="btn btn-primary">{discount ? "Salvar" : "Cadastrar"}</button>
      </div>
    </form>
  );
}
