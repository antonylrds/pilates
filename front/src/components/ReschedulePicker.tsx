import type { Schemas } from "@pilates/api-client";

import { api, call } from "../lib/api";
import { addDays, fmtHour, fmtShortDay, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { Loading } from "./ui";

export type CalendarEntry = Schemas["CalendarEntry"];

type Props = {
  fromGroupId: number;
  fromDate: string;
  selected?: { class_group_id: number; date: string } | null;
  onPick: (entry: CalendarEntry) => void;
};

/** Lista as aulas com vaga nos próximos 14 dias que ainda não começaram (destino de reposição). */
export function ReschedulePicker({ fromGroupId, fromDate, selected, onPick }: Props) {
  const today = todayISO();
  const start = fromDate > today ? fromDate : today;
  const end = toISO(addDays(parseISO(start), 13));
  const nowHour = new Date().getHours();
  const options = useAsync(
    () => call(api.GET("/api/v1/calendar", { params: { query: { date_from: start, date_to: end } } })),
    [start],
  );

  const hourOf = (e: CalendarEntry) => Number(e.starts_at.slice(11, 13));
  const available = (options.data ?? []).filter(
    (e) =>
      (e.status === "confirmed" || e.status === "inactive") &&
      e.available_spots > 0 &&
      !(e.class_group_id === fromGroupId && e.date === fromDate) &&
      (e.date > today || (e.date === today && hourOf(e) > nowHour)),
  );

  if (options.loading && !options.data) return <Loading />;
  if (available.length === 0) return <p className="muted small">Nenhuma aula com vaga nos próximos 14 dias.</p>;

  return (
    <div className="picker-list">
      {available.map((e) => {
        const isSelected = selected?.class_group_id === e.class_group_id && selected?.date === e.date;
        return (
          <button
            type="button"
            key={`${e.class_group_id}-${e.date}`}
            className={`picker-option ${isSelected ? "is-selected" : ""}`}
            onClick={() => onPick(e)}
          >
            <span>
              {fmtShortDay(e.date)} · {fmtHour(hourOf(e))}
            </span>
            <span className="muted small">
              {e.room.name} · {e.teacher.name.split(" ")[0]} · {e.available_spots} vaga(s)
            </span>
          </button>
        );
      })}
    </div>
  );
}
