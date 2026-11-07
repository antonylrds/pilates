import type { Schemas } from "@pilates/api-client";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, money, toISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

type Receipt = Schemas["CashReceipt"];
type Filter = "all" | Receipt["kind"];

const KIND_LABEL: Record<Receipt["kind"], string> = { plan: "Plano", service: "Serviço" };

function monthLabel(d: Date) {
  const label = d.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Caixa do estúdio: recebimentos, faturamento do mês e pagamento dos professores. */
export function CashPage() {
  const { isAdmin } = useSession();
  const now = new Date();
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [filter, setFilter] = useState<Filter>("all");

  const dateFrom = toISO(month);
  const dateTo = toISO(new Date(month.getFullYear(), month.getMonth() + 1, 0));
  const report = useAsync(
    () =>
      isAdmin
        ? call(api.GET("/api/v1/reports/cash", { params: { query: { date_from: dateFrom, date_to: dateTo } } }))
        : Promise.resolve(null),
    [dateFrom, isAdmin],
  );
  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));
  const isCurrent = month.getFullYear() === now.getFullYear() && month.getMonth() === now.getMonth();

  if (!isAdmin) {
    return (
      <div className="page">
        <h1>Caixa</h1>
        <p className="alert alert-warning">Apenas administradores podem ver o caixa do estúdio.</p>
      </div>
    );
  }

  const data = report.data;
  const receipts = (data?.receipts ?? []).filter((r) => filter === "all" || r.kind === filter);
  const shown = receipts.reduce((sum, r) => sum + Number(r.amount), 0);
  const net = Number(data?.net_total ?? 0);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Caixa</h1>
          <p className="muted">Recebimentos do estúdio, faturamento do mês e pagamento dos professores</p>
        </div>
        <div className="toolbar month-stepper">
          <button className="btn" onClick={() => shift(-1)} aria-label="Mês anterior">
            ‹
          </button>
          <strong className="month-name">{monthLabel(month)}</strong>
          <button className="btn" onClick={() => shift(1)} aria-label="Próximo mês">
            ›
          </button>
          {!isCurrent && (
            <button className="btn" onClick={() => setMonth(new Date(now.getFullYear(), now.getMonth(), 1))}>
              Mês atual
            </button>
          )}
        </div>
      </header>

      {report.loading && !data && <Loading />}
      {report.error && <ErrorBox message={report.error} />}

      {data && (
        <>
          <div className="stats">
            <div className="stat">
              <span className="stat-label">Faturamento do mês</span>
              <span className="stat-value">{money(data.received_total)}</span>
              <span className="muted small">
                Planos {money(data.plans_total)} · Serviços {money(data.services_total)}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Pago aos professores</span>
              <span className="stat-value text-danger">− {money(data.teacher_paid_total)}</span>
              <span className="muted small">Devido pelas aulas do mês: {money(data.teacher_payments_total)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Resultado</span>
              <span className={`stat-value ${net < 0 ? "text-danger" : "text-success"}`}>{money(data.net_total)}</span>
              <span className="muted small">Faturamento − pago aos professores</span>
            </div>
            <div className="stat">
              <span className="stat-label">A receber</span>
              <span className="stat-value">{money(data.pending_total)}</span>
              <span className="muted small">{data.pending.length} plano(s)/serviço(s) em aberto</span>
            </div>
          </div>

          <section className="card">
            <div className="card-title-row">
              <h3 className="card-title">
                Recebimentos <span className="muted small">({receipts.length})</span>
              </h3>
              <div className="segmented" role="group" aria-label="Filtrar recebimentos">
                {(["all", "plan", "service"] as Filter[]).map((f) => (
                  <button key={f} type="button" className={`seg ${filter === f ? "seg-present is-on" : ""}`} onClick={() => setFilter(f)}>
                    {f === "all" ? "Todos" : f === "plan" ? "Planos" : "Serviços"}
                  </button>
                ))}
              </div>
            </div>
            {receipts.length === 0 ? (
              <Empty>Nenhum recebimento neste mês.</Empty>
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Aluno</th>
                      <th>Descrição</th>
                      <th className="num">Tabela</th>
                      <th className="num">Desconto</th>
                      <th className="num">Recebido</th>
                    </tr>
                  </thead>
                  <tbody>
                    {receipts.map((r) => (
                      <tr key={`${r.kind}-${r.id}`}>
                        <td>{fmtDate(r.date)}</td>
                        <td>
                          <Link to={`/alunos/${r.student.id}`}>{r.student.name}</Link>
                        </td>
                        <td>
                          <Badge tone={r.kind === "plan" ? "info" : "neutral"}>{KIND_LABEL[r.kind]}</Badge> {r.description}
                          {r.detail && <div className="muted small">{r.detail}</div>}
                        </td>
                        <td className="num">{money(r.gross)}</td>
                        <td className="num">{Number(r.discount) > 0 ? `− ${money(r.discount)}` : "—"}</td>
                        <td className="num">
                          <strong>{money(r.amount)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4}>
                        {filter === "all" && Number(data.discounts_total) > 0 && (
                          <span className="muted small">Descontos concedidos no mês: {money(data.discounts_total)}</span>
                        )}
                      </td>
                      <td className="num muted">Total</td>
                      <td className="num">
                        <strong>{money(shown)}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-title-row">
              <h3 className="card-title">Pagamento de professores</h3>
              <Link to="/professores" className="small">
                Ver detalhes por aula →
              </Link>
            </div>
            {data.teachers.length === 0 ? (
              <Empty>Nenhuma aula, sessão finalizada ou pagamento a professor neste mês.</Empty>
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Professor</th>
                      <th className="num">Aulas</th>
                      <th className="num">Serviços</th>
                      <th className="num">Devido</th>
                      <th className="num">Pago</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.teachers.map((t) => (
                      <tr key={t.teacher.id}>
                        <td>{t.teacher.name}</td>
                        <td className="num">
                          {money(t.lessons_amount)} <span className="muted small">({t.lessons_given})</span>
                        </td>
                        <td className="num">
                          {money(t.services_amount)} <span className="muted small">({t.services_given})</span>
                        </td>
                        <td className="num">{money(t.amount)}</td>
                        <td className="num">
                          <strong>{Number(t.paid) > 0 ? `− ${money(t.paid)}` : "—"}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={3} className="num muted">
                        Total
                      </td>
                      <td className="num">{money(data.teacher_payments_total)}</td>
                      <td className="num text-danger">
                        <strong>− {money(data.teacher_paid_total)}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            <div className="cash-summary">
              <span>Faturamento {money(data.received_total)}</span>
              <span>− Pago aos professores {money(data.teacher_paid_total)}</span>
              <strong className={net < 0 ? "text-danger" : "text-success"}>= Resultado {money(data.net_total)}</strong>
            </div>
            <p className="muted small">
              Faturamento pela data do pagamento. Só entra como desconto o que foi pago aos professores no mês (pela data do
              pagamento); o devido é calculado pelas aulas e sessões finalizadas e serve de referência.
            </p>
            {data.teacher_payments.length > 0 && (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Professor</th>
                      <th>Observações</th>
                      <th className="num">Valor pago</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.teacher_payments.map((p) => (
                      <tr key={p.id}>
                        <td>{fmtDate(p.date)}</td>
                        <td>{p.teacher.name}</td>
                        <td className="small">{p.notes || <span className="muted">—</span>}</td>
                        <td className="num">− {money(p.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h3 className="card-title">
              A receber <span className="muted small">({data.pending.length}, de qualquer mês)</span>
            </h3>
            {data.pending.length === 0 ? (
              <Empty>Nenhum plano ou serviço em aberto.</Empty>
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Desde</th>
                      <th>Aluno</th>
                      <th>Descrição</th>
                      <th className="num">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pending.map((p) => (
                      <tr key={`${p.kind}-${p.id}`}>
                        <td>{fmtDate(p.since)}</td>
                        <td>
                          <Link to={`/alunos/${p.student.id}`}>{p.student.name}</Link>
                        </td>
                        <td>
                          <Badge tone={p.kind === "plan" ? "info" : "neutral"}>{KIND_LABEL[p.kind]}</Badge> {p.description}
                        </td>
                        <td className="num">{money(p.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small">Para registrar um pagamento, abra a ficha do aluno e marque o plano ou serviço como pago.</p>
          </section>
        </>
      )}
    </div>
  );
}
