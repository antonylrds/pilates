import type { Schemas } from "@pilates/api-client";

import { fmtHour } from "../lib/format";

type Group = Schemas["ClassGroupRead"];
const WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];

type Props = {
  groups: Group[];
  selected: number[];
  /** Turmas em que o aluno já está (ocupam vaga dele mesmo). */
  ownGroupIds?: number[];
  limit: number;
  onChange: (ids: number[]) => void;
};

/** Seleção de turmas padrão em grade semanal, respeitando o limite do plano, a lotação e horários repetidos. */
export function GroupPicker({ groups, selected, ownGroupIds = [], limit, onChange }: Props) {
  const selectedGroups = groups.filter((g) => selected.includes(g.id));
  const takenSlots = new Set(selectedGroups.map((g) => `${g.weekday}-${g.start_hour}`));

  function toggle(g: Group) {
    if (selected.includes(g.id)) onChange(selected.filter((id) => id !== g.id));
    else onChange([...selected, g.id]);
  }

  return (
    <div className="group-picker">
      {WEEKDAYS.map((day, wd) => {
        const dayGroups = groups.filter((g) => g.weekday === wd).sort((a, b) => a.start_hour - b.start_hour);
        return (
          <div key={day} className="gp-col">
            <div className="gp-day">{day}</div>
            {dayGroups.length === 0 && <div className="muted small gp-empty">—</div>}
            {dayGroups.map((g) => {
              const isSelected = selected.includes(g.id);
              const own = ownGroupIds.includes(g.id);
              const free = g.capacity - g.enrolled_count + (own ? 1 : 0);
              const reason = isSelected
                ? null
                : free <= 0
                  ? "Lotada"
                  : takenSlots.has(`${g.weekday}-${g.start_hour}`)
                    ? "Horário já escolhido"
                    : selected.length >= limit
                      ? "Limite do plano"
                      : null;
              return (
                <button
                  type="button"
                  key={g.id}
                  className={`gp-item ${isSelected ? "is-selected" : ""}`}
                  disabled={reason !== null}
                  title={reason ?? `${g.display_name} · ${g.teacher.name}`}
                  onClick={() => toggle(g)}
                >
                  <span className="gp-time">{fmtHour(g.start_hour)}</span>
                  <span className="gp-room">{g.room.name}</span>
                  <span className="gp-meta">
                    {g.teacher.name.split(" ")[0]} · {reason === "Lotada" ? "lotada" : `${Math.max(free, 0)} vaga(s)`}
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
