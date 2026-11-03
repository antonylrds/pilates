import { api, call } from "../lib/api";
import { fmtDate, money } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { subscriptionUsage, usageTone } from "../lib/labels";
import { Badge, ErrorBox, Loading } from "./ui";

/** Histórico de planos do aluno, com os valores congelados na contratação. */
export function PlanHistory({ studentId, version }: { studentId: number; version: number }) {
  const history = useAsync(
    () =>
      call(api.GET("/api/v1/students/{student_id}/subscriptions", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );

  return (
    <div className="card">
      <h3 className="card-title">
        Histórico de planos{" "}
        <span className="muted small">(valores da contratação; reajustes posteriores não alteram)</span>
      </h3>
      {history.loading && !history.data && <Loading />}
      {history.error && <ErrorBox message={history.error} />}
      {history.data?.length === 0 && <p className="muted">Nenhum plano contratado.</p>}
      {history.data && history.data.length > 0 && (
        <div className="table-scroll">
          <table className="table history-table">
            <thead>
              <tr>
                <th>Plano</th>
                <th>Contratado</th>
                <th className="num">Valor pago</th>
                <th className="num">Por aula</th>
                <th>Aulas</th>
                <th>Período de uso</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {history.data.map((h) => (
                <tr key={h.id} className={h.usage === "in_use" ? "is-current" : ""}>
                  <td>
                    <strong>{h.plan_name ?? h.plan.name}</strong>
                    <div className="muted small">{h.sessions_per_week}x por semana</div>
                  </td>
                  <td>{fmtDate(h.start_date)}</td>
                  <td className="num">
                    {money(h.final_price)}
                    {Number(h.discount_amount) > 0 && (
                      <div className="muted small">
                        {money(h.base_price)} − {money(h.discount_amount)}
                        {h.discount_name && <> ({h.discount_name})</>}
                      </div>
                    )}
                  </td>
                  <td className="num">{money(h.price_per_lesson)}</td>
                  <td>
                    {h.credits_used}/{h.total_classes}
                    {h.usage !== "cancelled" && h.credits_remaining > 0 && (
                      <div className="muted small">{h.credits_remaining} restante(s)</div>
                    )}
                  </td>
                  <td className="small">
                    {h.first_lesson_date ? (
                      <>
                        {fmtDate(h.first_lesson_date)}
                        {h.last_lesson_date && h.last_lesson_date !== h.first_lesson_date && (
                          <> a {fmtDate(h.last_lesson_date)}</>
                        )}
                      </>
                    ) : (
                      <span className="muted">{h.usage === "queued" ? "Após o plano em uso" : "—"}</span>
                    )}
                  </td>
                  <td>
                    <Badge tone={usageTone[h.usage]}>{subscriptionUsage[h.usage]}</Badge>
                    <div className="small">
                      {h.is_paid ? (
                        <span className="text-success">Pago{h.paid_at && ` ${fmtDate(h.paid_at)}`}</span>
                      ) : (
                        h.usage !== "cancelled" && <span className="text-warning">Pendente</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
