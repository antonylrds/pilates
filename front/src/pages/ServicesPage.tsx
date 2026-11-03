import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useState } from "react";

import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { money } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

type Service = Schemas["ServiceRead"];
type Overview = Schemas["CatalogOverview"];

/** Aba "Serviços avulsos" da tela Planos e serviços. */
export function ServicesTab({ overview, onChanged }: { overview?: Overview; onChanged: () => void }) {
  const { isAdmin } = useSession();
  const [showInactive, setShowInactive] = useState(false);
  const services = useAsync(async () => {
    const active = await call(api.GET("/api/v1/services", { params: { query: { is_active: true } } }));
    if (!showInactive) return active;
    const inactive = await call(api.GET("/api/v1/services", { params: { query: { is_active: false } } }));
    return [...active, ...inactive];
  }, [showInactive]);
  const [editing, setEditing] = useState<Service | "new" | null>(null);
  const usage = (id: number) => overview?.services.find((s) => s.service_id === id);
  const reload = () => {
    services.reload();
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
            + Novo serviço
          </button>
        )}
      </div>
      <p className="muted small tab-hint">
        Fisioterapia, RPG e outros atendimentos contratados à parte do plano. O valor é o sugerido na contratação.
      </p>

      {services.loading && !services.data && <Loading />}
      {services.error && <ErrorBox message={services.error} />}
      {services.data?.length === 0 && <Empty>Nenhum serviço cadastrado.</Empty>}

      {editing === "new" && (
        <ServiceForm
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}

      <ul className="stack">
        {(services.data ?? []).map((s) => {
          if (editing !== "new" && editing?.id === s.id) {
            return (
              <li key={s.id}>
                <ServiceForm
                  service={s}
                  onCancel={() => setEditing(null)}
                  onSaved={() => {
                    setEditing(null);
                    reload();
                  }}
                />
              </li>
            );
          }
          const u = usage(s.id);
          return (
            <li key={s.id} className={`card catalog-row ${s.is_active ? "" : "is-inactive"}`}>
              <div className="catalog-main">
                <div>
                  <strong>{s.name}</strong> {!s.is_active && <Badge tone="neutral">Inativo</Badge>}
                </div>
                {s.description && <p className="muted small">{s.description}</p>}
                {u && (
                  <div className="usage">
                    <span className="usage-chip">{u.active_contracts} contratação(ões) em andamento</span>
                    {u.upcoming_sessions > 0 && <span className="usage-chip">{u.upcoming_sessions} sessão(ões) agendada(s)</span>}
                  </div>
                )}
              </div>
              <span className="catalog-price">
                {money(s.price)}
                <span className="muted small"> /sessão</span>
              </span>
              {isAdmin && (
                <span className="catalog-actions">
                  <button className="btn btn-sm" onClick={() => setEditing(s)}>
                    Editar
                  </button>
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={async () => {
                      await call(
                        api.PATCH("/api/v1/services/{service_id}", {
                          params: { path: { service_id: s.id } },
                          body: { is_active: !s.is_active },
                        }),
                      );
                      reload();
                    }}
                  >
                    {s.is_active ? "Desativar" : "Reativar"}
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

function ServiceForm({ service, onCancel, onSaved }: { service?: Service; onCancel: () => void; onSaved: () => void }) {
  const [name, setName] = useState(service?.name ?? "");
  const [price, setPrice] = useState(service?.price ?? "");
  const [description, setDescription] = useState(service?.description ?? "");
  const [error, setError] = useState<string>();

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    try {
      const body = { name, price: price || "0", description: description || null };
      if (service) {
        await call(api.PATCH("/api/v1/services/{service_id}", { params: { path: { service_id: service.id } }, body }));
      } else {
        await call(api.POST("/api/v1/services", { body }));
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
          <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Ex.: Fisioterapia" />
        </label>
        <label className="field">
          <span>Valor padrão por sessão</span>
          <div className="input-money">
            <span>R$</span>
            <input type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} required />
          </div>
        </label>
      </div>
      <label className="field">
        <span>Descrição (opcional)</span>
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {service && <p className="muted small">Alterar o valor não muda serviços já contratados.</p>}
      {error && <ErrorBox message={error} />}
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancelar
        </button>
        <button className="btn btn-primary">{service ? "Salvar" : "Cadastrar"}</button>
      </div>
    </form>
  );
}
