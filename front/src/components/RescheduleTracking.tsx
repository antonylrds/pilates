import type { Schemas } from "@pilates/api-client";

import { api, call } from "../lib/api";
import { fmtHour, fmtShortDay } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { attendanceStatus, attendanceTone } from "../lib/labels";
import { Badge, ErrorBox, Loading } from "./ui";

type Ref = Schemas["LessonRef"];

const label = (l: Ref) => `${fmtShortDay(l.date)} ${fmtHour(l.start_hour)}`;

type Props = { studentId: number; version: number; onOpenLesson: (groupId: number, date: string) => void };

/** Acompanhamento: cada aula original do aluno e quantas vezes ela foi reagendada. */
export function RescheduleTracking({ studentId, version, onOpenLesson }: Props) {
  const chains = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}/reschedules", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );
  const total = (chains.data ?? []).reduce((n, c) => n + c.reschedule_count, 0);

  return (
    <div className="card">
      <h3 className="card-title">
        Reagendamentos{" "}
        {chains.data && chains.data.length > 0 && (
          <span className="muted small">
            ({chains.data.length} aula(s), {total} reagendamento(s) no total)
          </span>
        )}
      </h3>
      {chains.loading && !chains.data && <Loading />}
      {chains.error && <ErrorBox message={chains.error} />}
      {chains.data?.length === 0 && <p className="muted">Nenhuma aula reagendada.</p>}
      <ul className="chains">
        {(chains.data ?? []).map((c) => {
          const waiting = c.current_status === "pending";
          return (
            <li key={`${c.original_lesson.class_group_id}-${c.original_lesson.date}`} className="chain">
              <div className="chain-head">
                <span>
                  Aula de <strong>{label(c.original_lesson)}</strong>
                </span>
                <span className={`resched-count ${c.reschedule_count >= 2 ? "is-high" : ""}`}>
                  ↻ reagendada {c.reschedule_count}x
                </span>
              </div>
              <ol className="chain-steps">
                {c.steps.map((s, i) => (
                  <li key={i}>
                    <button
                      className="link-button"
                      onClick={() => onOpenLesson(s.to_lesson.class_group_id, s.to_lesson.date)}
                    >
                      → {label(s.to_lesson)}
                    </button>
                    {s.justification && <span className="muted small"> · “{s.justification}”</span>}
                  </li>
                ))}
              </ol>
              <div className="chain-foot">
                <span className="muted small">Situação atual:</span>
                <Badge tone={waiting ? "info" : attendanceTone[c.current_status]}>
                  {waiting ? "Aguardando aula" : attendanceStatus[c.current_status]}
                </Badge>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
