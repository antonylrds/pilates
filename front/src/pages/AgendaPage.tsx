import type { Schemas } from "@pilates/api-client";
import { useState } from "react";

import { DateInput } from "../components/DateInput";
import { LessonPanel } from "../components/LessonPanel";
import { ServiceSessionPanel } from "../components/ServiceSessionPanel";
import { ErrorBox } from "../components/ui";
import { api, call } from "../lib/api";
import { addDays, fmtDate, fmtHour, fmtShortDay, mondayOf, parseISO, toISO, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { lessonStatus } from "../lib/labels";
import { useSession } from "../lib/session";

type Entry = Schemas["CalendarEntry"];

/** Aula com alunos, já iniciada e ainda não concluída: alguém precisa registrar a presença. */
function needsAttention(e: Entry, loadedAt: number): boolean {
  const hasStudents = e.kind === "service" ? e.student != null : e.attendees_count > 0;
  return e.status === "confirmed" && hasStudents && new Date(e.starts_at).getTime() < loadedAt;
}

const ATTENTION_TITLE = "Aula já passou e ainda não foi concluída";

export function AgendaPage() {
  const { session } = useSession();
  // Momento em que a página foi carregada: define o que já ficou para trás.
  const [loadedAt] = useState(() => Date.now());
  const [monday, setMonday] = useState(() => mondayOf(new Date()));
  // Data escolhida no campo de data (destacada na grade).
  const [picked, setPicked] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ groupId: number; date: string } | null>(null);
  const [selectedService, setSelectedService] = useState<number | null>(null);
  const days = [0, 1, 2, 3, 4].map((i) => toISO(addDays(monday, i)));
  const open_ = (e: Entry) =>
    e.kind === "service" && e.service_session_id != null
      ? setSelectedService(e.service_session_id)
      : e.class_group_id != null && setSelected({ groupId: e.class_group_id, date: e.date });

  const calendar = useAsync(
    () => call(api.GET("/api/v1/calendar", { params: { query: { date_from: days[0], date_to: days[4] } } })),
    [days[0]],
  );

  const open = session?.studio.open_hour ?? 6;
  const close = session?.studio.close_hour ?? 19;
  const hours = Array.from({ length: close - open }, (_, i) => open + i);
  const today = todayISO();

  const cell = (day: string, hour: number): Entry[] =>
    (calendar.data ?? []).filter((e) => e.date === day && Number(e.starts_at.slice(11, 13)) === hour);

  const goTo = (iso: string) => {
    setPicked(iso);
    setMonday(mondayOf(parseISO(iso)));
  };
  const shiftWeek = (weeks: number) => {
    setPicked(null);
    setMonday(addDays(monday, weeks * 7));
  };
  const pickedIsWeekend = picked !== null && parseISO(picked).getDay() % 6 === 0;
  const dateValue = picked ?? (days.includes(today) ? today : days[0]);

  const totals = (calendar.data ?? []).reduce(
    (acc, e) => ({ ...acc, [e.status]: (acc[e.status] ?? 0) + 1 }),
    {} as Record<string, number>,
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Agenda</h1>
          <p className="muted">
            Semana de {fmtDate(days[0])} a {fmtDate(days[4])}
          </p>
        </div>
        <div className="toolbar">
          <DateInput
            className="date-jump"
            value={dateValue}
            onChange={(iso) => iso && goTo(iso)}
            aria-label="Ir para a data"
            title="Ir para uma data específica"
          />
          <button className="btn" onClick={() => shiftWeek(-1)} aria-label="Semana anterior">
            ‹
          </button>
          <button className="btn" onClick={() => goTo(today)}>
            Hoje
          </button>
          <button className="btn" onClick={() => shiftWeek(1)} aria-label="Próxima semana">
            ›
          </button>
        </div>
      </header>
      {pickedIsWeekend && (
        <div className="alert alert-info">
          {fmtDate(picked!)} é fim de semana; o estúdio funciona de segunda a sexta. Mostrando a semana correspondente.
        </div>
      )}

      <div className="legend">
        {(["confirmed", "completed", "inactive", "cancelled"] as const).map((s) => (
          <span key={s} className="legend-item">
            <span className={`dot dot-${s}`} /> {lessonStatus[s]} <b>{totals[s] ?? 0}</b>
          </span>
        ))}
        <span className="legend-item">
          <span className="dot dot-service" /> Serviço avulso
        </span>
      </div>

      {calendar.error && <ErrorBox message={calendar.error} />}

      <div className={`calendar ${calendar.loading ? "is-loading" : ""}`}>
        <div className="cal-corner" />
        {days.map((d) => (
          <div key={d} className={`cal-day ${d === today ? "is-today" : ""} ${d === picked ? "is-picked" : ""}`}>
            {fmtShortDay(d)}
          </div>
        ))}
        {hours.map((h) => (
          <div className="cal-row" key={h}>
            <div className="cal-hour">{fmtHour(h)}</div>
            {days.map((d) => (
              <div key={d} className={`cal-cell ${d === today ? "is-today" : ""} ${d === picked ? "is-picked" : ""}`}>
                {cell(d, h).map((e) =>
                  e.kind === "service" ? (
                    <button
                      key={`s-${e.service_session_id}`}
                      className={`lesson-chip service-chip chip-${e.status}`}
                      onClick={() => open_(e)}
                      title={`${e.class_group_name} · ${e.room.name} · ${e.teacher.name}`}
                    >
                      <span className="chip-room">✚ {e.class_group_name.split(" · ")[0]}</span>
                      <span className="chip-teacher">
                        {e.student?.name.split(" ")[0]} · {e.teacher.name.split(" ")[0]}
                      </span>
                      <span className="chip-count">
                        {needsAttention(e, loadedAt) ? (
                          <span className="chip-alert" title={ATTENTION_TITLE} aria-label={ATTENTION_TITLE}>
                            !
                          </span>
                        ) : e.status === "completed" ? (
                          "✓"
                        ) : e.status === "cancelled" ? (
                          "—"
                        ) : (
                          ""
                        )}
                      </span>
                    </button>
                  ) : (
                    <button
                      key={`l-${e.class_group_id}`}
                      className={`lesson-chip chip-${e.status}`}
                      onClick={() => open_(e)}
                      title={`${e.class_group_name} · ${e.teacher.name}`}
                    >
                      <span className="chip-room">{e.room.name}</span>
                      <span className="chip-teacher">{e.teacher.name.split(" ")[0]}</span>
                      <span className="chip-count">
                        {needsAttention(e, loadedAt) && (
                          <span className="chip-alert" title={ATTENTION_TITLE} aria-label={ATTENTION_TITLE}>
                            !
                          </span>
                        )}
                        {e.status === "cancelled" ? "—" : `${e.attendees_count}/${e.capacity}`}
                      </span>
                    </button>
                  ),
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {selected && (
        <LessonPanel
          groupId={selected.groupId}
          date={selected.date}
          onClose={() => setSelected(null)}
          onChanged={calendar.reload}
        />
      )}
      {selectedService != null && (
        <ServiceSessionPanel
          sessionId={selectedService}
          onClose={() => setSelectedService(null)}
          onChanged={calendar.reload}
        />
      )}
    </div>
  );
}
