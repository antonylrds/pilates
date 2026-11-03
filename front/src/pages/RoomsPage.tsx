import type { Schemas } from "@pilates/api-client";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Modal } from "../components/Modal";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { api, call } from "../lib/api";
import { fmtDate, fmtHour, todayISO } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";

type Room = Schemas["RoomRead"];
type Group = Schemas["ClassGroupRead"];
type Teacher = Schemas["TeacherRead"];

const WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];

type Editing =
  | { mode: "create"; room: Room; weekday: number; hour: number }
  | { mode: "edit"; group: Group };

export function RoomsPage() {
  const { session, isAdmin } = useSession();
  const [showInactive, setShowInactive] = useState(false);
  const rooms = useAsync(
    () => call(api.GET("/api/v1/rooms", { params: { query: { is_active: showInactive ? null : true } } })),
    [showInactive],
  );
  const groups = useAsync(() => call(api.GET("/api/v1/class-groups")), []);
  const teachers = useAsync(() => call(api.GET("/api/v1/teachers")), []);
  const [roomId, setRoomId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);

  const activeRooms = (rooms.data ?? []).filter((r) => r.is_active);
  useEffect(() => {
    if (roomId === null && activeRooms.length) setRoomId(activeRooms[0].id);
  }, [activeRooms, roomId]);

  const room = (rooms.data ?? []).find((r) => r.id === roomId) ?? null;
  const allGroups = groups.data ?? [];
  const reloadAll = () => {
    rooms.reload();
    groups.reload();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Salas e turmas</h1>
          <p className="muted">
            Turmas de 1h, de segunda a sexta. Uma sala não pode ter duas turmas no mesmo horário.
          </p>
        </div>
      </header>

      {(rooms.error || groups.error) && <ErrorBox message={(rooms.error || groups.error)!} />}

      <div className="rooms-layout">
        <div className="stack">
          {session && <StudioHoursCard studio={session.studio} canEdit={isAdmin} />}
          <RoomsCard
            rooms={rooms.data ?? []}
            groups={allGroups}
            selectedId={roomId}
            onSelect={setRoomId}
            canEdit={isAdmin}
            showInactive={showInactive}
            onToggleInactive={() => setShowInactive((v) => !v)}
            onChanged={reloadAll}
          />
        </div>

        <section className="card">
          {rooms.loading && !rooms.data ? (
            <Loading />
          ) : room ? (
            <RoomGrid
              room={room}
              groups={allGroups.filter((g) => g.room.id === room.id)}
              openHour={session?.studio.open_hour ?? 6}
              closeHour={session?.studio.close_hour ?? 19}
              canEdit={isAdmin && room.is_active}
              onCreate={(weekday, hour) => setEditing({ mode: "create", room, weekday, hour })}
              onOpen={(group) => setEditing({ mode: "edit", group })}
            />
          ) : (
            <Empty>Cadastre uma sala para montar a grade de turmas.</Empty>
          )}
        </section>
      </div>

      {editing && (
        <GroupModal
          editing={editing}
          rooms={activeRooms}
          teachers={(teachers.data ?? []).filter((t) => t.is_active)}
          groups={allGroups}
          canEdit={isAdmin}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            groups.reload();
          }}
        />
      )}
    </div>
  );
}

// ---------- Funcionamento ----------
function StudioHoursCard({ studio, canEdit }: { studio: Schemas["StudioRead"]; canEdit: boolean }) {
  const { updateStudio } = useSession();
  const [open, setOpen] = useState(studio.open_hour);
  const [close, setClose] = useState(studio.close_hour);
  const [absence, setAbsence] = useState(studio.absence_consumes_credit);
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const dirty =
    open !== studio.open_hour || close !== studio.close_hour || absence !== studio.absence_consumes_credit;

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    try {
      const updated = await call(
        api.PATCH("/api/v1/studio", { body: { open_hour: open, close_hour: close, absence_consumes_credit: absence } }),
      );
      updateStudio(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const hourOptions = Array.from({ length: 25 }, (_, h) => h);

  return (
    <form className="card" onSubmit={save}>
      <h3 className="card-title">Funcionamento</h3>
      <div className="form-row">
        <label className="field">
          <span>Abre às</span>
          <select value={open} onChange={(e) => setOpen(Number(e.target.value))} disabled={!canEdit}>
            {hourOptions.slice(0, 24).map((h) => (
              <option key={h} value={h}>
                {fmtHour(h)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Fecha às</span>
          <select value={close} onChange={(e) => setClose(Number(e.target.value))} disabled={!canEdit}>
            {hourOptions.slice(1).map((h) => (
              <option key={h} value={h}>
                {fmtHour(h)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted small">
        Última turma começa às {fmtHour(close - 1)}. Dias: segunda a sexta.
      </p>
      <label className="check">
        <input type="checkbox" checked={absence} onChange={(e) => setAbsence(e.target.checked)} disabled={!canEdit} />
        <span>Falta consome aula do plano</span>
      </label>
      {error && <ErrorBox message={error} />}
      {canEdit && (
        <button className="btn btn-primary btn-block" disabled={!dirty}>
          {saved ? "Salvo ✓" : "Salvar"}
        </button>
      )}
    </form>
  );
}

// ---------- Salas ----------
function RoomsCard(props: {
  rooms: Room[];
  groups: Group[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  canEdit: boolean;
  showInactive: boolean;
  onToggleInactive: () => void;
  onChanged: () => void;
}) {
  const { rooms, groups, selectedId, onSelect, canEdit, showInactive, onToggleInactive, onChanged } = props;
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState(3);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editCapacity, setEditCapacity] = useState(1);
  const [error, setError] = useState<string>();

  async function run(action: () => Promise<unknown>) {
    setError(undefined);
    try {
      await action();
      onChanged();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    const ok = await run(() => call(api.POST("/api/v1/rooms", { body: { name, capacity } })));
    if (ok) setName("");
  }

  async function saveEdit(room: Room) {
    const ok = await run(() =>
      call(
        api.PATCH("/api/v1/rooms/{room_id}", {
          params: { path: { room_id: room.id } },
          body: { name: editName, capacity: editCapacity },
        }),
      ),
    );
    if (ok) setEditId(null);
  }

  const deactivate = (room: Room) =>
    window.confirm(`Desativar a sala ${room.name}?`) &&
    run(() => call(api.DELETE("/api/v1/rooms/{room_id}", { params: { path: { room_id: room.id } } })));

  const reactivate = (room: Room) =>
    run(() =>
      call(api.PATCH("/api/v1/rooms/{room_id}", { params: { path: { room_id: room.id } }, body: { is_active: true } })),
    );

  return (
    <div className="card">
      <div className="card-title-row">
        <h3 className="card-title">Salas</h3>
        <label className="check small">
          <input type="checkbox" checked={showInactive} onChange={onToggleInactive} />
          <span>Mostrar inativas</span>
        </label>
      </div>

      <ul className="room-list">
        {rooms.map((room) => {
          const count = groups.filter((g) => g.room.id === room.id).length;
          if (editId === room.id) {
            return (
              <li key={room.id} className="room-item is-editing">
                <input value={editName} onChange={(e) => setEditName(e.target.value)} aria-label="Nome da sala" />
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={editCapacity}
                  onChange={(e) => setEditCapacity(Number(e.target.value))}
                  aria-label="Capacidade"
                  className="input-narrow"
                />
                <button className="btn btn-sm btn-primary" onClick={() => saveEdit(room)}>
                  Salvar
                </button>
                <button className="btn btn-sm btn-ghost" onClick={() => setEditId(null)}>
                  ✕
                </button>
              </li>
            );
          }
          return (
            <li key={room.id}>
              <div
                className={`room-item ${room.id === selectedId ? "is-active" : ""} ${room.is_active ? "" : "is-inactive"}`}
              >
                <button className="room-select" onClick={() => onSelect(room.id)}>
                  <span className="list-title">{room.name}</span>
                  <span className="muted small">
                    {room.capacity} aluno(s) · {count} turma(s)
                  </span>
                </button>
                {!room.is_active && <Badge tone="neutral">Inativa</Badge>}
                {canEdit && room.is_active && (
                  <span className="room-actions">
                    <button
                      className="btn btn-sm btn-ghost"
                      title="Editar"
                      onClick={() => {
                        setEditId(room.id);
                        setEditName(room.name);
                        setEditCapacity(room.capacity);
                      }}
                    >
                      ✎
                    </button>
                    <button className="btn btn-sm btn-ghost" title="Desativar" onClick={() => deactivate(room)}>
                      🗑
                    </button>
                  </span>
                )}
                {canEdit && !room.is_active && (
                  <button className="btn btn-sm" onClick={() => reactivate(room)}>
                    Reativar
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {error && <ErrorBox message={error} />}

      {canEdit && (
        <form className="room-form" onSubmit={create}>
          <input placeholder="Nova sala" value={name} onChange={(e) => setName(e.target.value)} required />
          <input
            type="number"
            min={1}
            max={50}
            value={capacity}
            onChange={(e) => setCapacity(Number(e.target.value))}
            className="input-narrow"
            aria-label="Capacidade"
            title="Capacidade"
          />
          <button className="btn btn-primary">Adicionar</button>
        </form>
      )}
    </div>
  );
}

// ---------- Grade semanal da sala ----------
function RoomGrid(props: {
  room: Room;
  groups: Group[];
  openHour: number;
  closeHour: number;
  canEdit: boolean;
  onCreate: (weekday: number, hour: number) => void;
  onOpen: (group: Group) => void;
}) {
  const { room, groups, openHour, closeHour, canEdit, onCreate, onOpen } = props;
  const hours = Array.from({ length: closeHour - openHour }, (_, i) => openHour + i);
  const at = (weekday: number, hour: number) => groups.find((g) => g.weekday === weekday && g.start_hour === hour);
  const outside = groups.filter((g) => g.start_hour < openHour || g.start_hour >= closeHour);
  const free = hours.length * 5 - groups.length + outside.length;

  return (
    <>
      <div className="card-title-row">
        <div>
          <h3 className="card-title">Grade da sala {room.name}</h3>
          <p className="muted small">
            {groups.length} turma(s) · {free} horário(s) livre(s) · capacidade {room.capacity}
          </p>
        </div>
        {canEdit && <span className="muted small">Clique em um horário livre para criar uma turma.</span>}
      </div>

      <div className="room-grid">
        <div />
        {WEEKDAYS.map((d) => (
          <div key={d} className="rg-day">
            {d}
          </div>
        ))}
        {hours.map((h) => (
          <div className="cal-row" key={h}>
            <div className="rg-hour">{fmtHour(h)}</div>
            {WEEKDAYS.map((_, wd) => {
              const group = at(wd, h);
              if (group) {
                const full = group.enrolled_count >= group.capacity;
                return (
                  <button key={wd} className="rg-cell rg-busy" onClick={() => onOpen(group)} title={group.display_name}>
                    <span className="rg-teacher">{group.teacher.name}</span>
                    <span className={`rg-count ${full ? "is-full" : ""}`}>
                      {group.enrolled_count}/{group.capacity}
                    </span>
                    {group.name && <span className="rg-name">{group.name}</span>}
                  </button>
                );
              }
              return canEdit ? (
                <button key={wd} className="rg-cell rg-free" onClick={() => onCreate(wd, h)} aria-label="Criar turma">
                  <span>+</span>
                </button>
              ) : (
                <div key={wd} className="rg-cell rg-free-static" />
              );
            })}
          </div>
        ))}
      </div>
    </>
  );
}

// ---------- Criar / editar turma ----------
function GroupModal(props: {
  editing: Editing;
  rooms: Room[];
  teachers: Teacher[];
  groups: Group[];
  canEdit: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { editing, rooms, teachers, groups, canEdit, onClose, onSaved } = props;
  const isCreate = editing.mode === "create";
  const base = isCreate ? null : editing.group;
  const weekday = isCreate ? editing.weekday : base!.weekday;
  const hour = isCreate ? editing.hour : base!.start_hour;
  const initialRoom = isCreate ? editing.room : rooms.find((r) => r.id === base!.room.id);

  const [teacherId, setTeacherId] = useState<number | "">(base?.teacher.id ?? "");
  const [roomId, setRoomId] = useState<number>(initialRoom?.id ?? base!.room.id);
  const [capacity, setCapacity] = useState<number>(base?.capacity ?? initialRoom?.capacity ?? 1);
  const [name, setName] = useState(base?.name ?? "");
  const [startDate, setStartDate] = useState(todayISO());
  const [endDate, setEndDate] = useState(todayISO());
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const detail = useAsync(
    () =>
      base
        ? call(api.GET("/api/v1/class-groups/{group_id}", { params: { path: { group_id: base.id } } }))
        : Promise.resolve(null),
    [base?.id],
  );

  const sameSlot = groups.filter((g) => g.weekday === weekday && g.start_hour === hour && g.id !== base?.id);
  const busyTeachers = new Set(sameSlot.map((g) => g.teacher.id));
  const busyRooms = new Set(sameSlot.map((g) => g.room.id));
  const selectedRoom = rooms.find((r) => r.id === roomId);
  const maxCapacity = selectedRoom?.capacity ?? capacity;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (teacherId === "") return setError("Selecione o professor");
    if (isCreate) {
      run(() =>
        call(
          api.POST("/api/v1/class-groups", {
            body: {
              room_id: roomId,
              teacher_id: teacherId,
              weekday,
              start_hour: hour,
              capacity,
              name: name || null,
              start_date: startDate,
            },
          }),
        ),
      );
    } else {
      run(() =>
        call(
          api.PATCH("/api/v1/class-groups/{group_id}", {
            params: { path: { group_id: base!.id } },
            body: { teacher_id: teacherId, room_id: roomId, capacity, name: name || null },
          }),
        ),
      );
    }
  }

  function endGroup() {
    if (!base || !window.confirm(`Encerrar a turma a partir de ${fmtDate(endDate)}? Os alunos serão liberados.`)) return;
    run(() =>
      call(
        api.DELETE("/api/v1/class-groups/{group_id}", {
          params: { path: { group_id: base.id }, query: { end_date: endDate } },
        }),
      ),
    );
  }

  const title = isCreate ? "Nova turma" : base!.display_name;
  const subtitle = `${WEEKDAYS[weekday]}, ${fmtHour(hour)} – ${fmtHour(hour + 1)}`;

  return (
    <Modal
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        canEdit && (
          <>
            {!isCreate && (
              <div className="end-group">
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} aria-label="Encerrar em" />
                <button type="button" className="btn btn-danger-outline" disabled={busy} onClick={endGroup}>
                  Encerrar turma
                </button>
              </div>
            )}
            <button type="submit" form="group-form" className="btn btn-primary" disabled={busy}>
              {isCreate ? "Criar turma" : "Salvar"}
            </button>
          </>
        )
      }
    >
      <form id="group-form" onSubmit={submit}>
        <div className="form-row">
          <label className="field">
            <span>Professor</span>
            <select
              value={teacherId}
              onChange={(e) => setTeacherId(e.target.value ? Number(e.target.value) : "")}
              disabled={!canEdit}
              required
            >
              <option value="">Selecione…</option>
              {teachers.map((t) => (
                <option key={t.id} value={t.id} disabled={busyTeachers.has(t.id)}>
                  {t.name}
                  {busyTeachers.has(t.id) ? " (ocupado neste horário)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Sala</span>
            <select
              value={roomId}
              onChange={(e) => {
                const next = Number(e.target.value);
                setRoomId(next);
                const r = rooms.find((x) => x.id === next);
                if (r && capacity > r.capacity) setCapacity(r.capacity);
              }}
              disabled={!canEdit}
            >
              {rooms.map((r) => (
                <option key={r.id} value={r.id} disabled={busyRooms.has(r.id)}>
                  {r.name}
                  {busyRooms.has(r.id) ? " (ocupada)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>Capacidade (máx. {maxCapacity})</span>
            <input
              type="number"
              min={Math.max(1, detail.data?.enrolled_count ?? 1)}
              max={maxCapacity}
              value={capacity}
              onChange={(e) => setCapacity(Number(e.target.value))}
              disabled={!canEdit}
            />
          </label>
          {isCreate ? (
            <label className="field">
              <span>Começa em</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
          ) : (
            <div className="field">
              <span>Desde</span>
              <div className="field-value">{fmtDate(base!.start_date)}</div>
            </div>
          )}
        </div>
        <label className="field">
          <span>Nome (opcional)</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={`${WEEKDAYS[weekday]} ${String(hour).padStart(2, "0")}h - ${selectedRoom?.name ?? ""}`}
            disabled={!canEdit}
          />
        </label>
      </form>

      {error && <ErrorBox message={error} />}

      {!isCreate && (
        <div className="group-students">
          <h3 className="section-title">
            Alunos fixos{" "}
            {detail.data && (
              <span className="muted small">
                ({detail.data.enrolled_count}/{detail.data.capacity})
              </span>
            )}
          </h3>
          {detail.loading && !detail.data && <Loading />}
          {detail.data?.students.length === 0 && <p className="muted small">Nenhum aluno nesta turma.</p>}
          <ul className="chips">
            {detail.data?.students.map((s) => (
              <li key={s.id}>
                <Link to={`/alunos/${s.id}`} className="chip">
                  {s.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
