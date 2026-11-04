"""Turmas, horários padrão dos alunos, calendário e lista de alunos de cada aula."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.central import Studio
from app.models.tenant import Attendance, ClassGroup, Enrollment, Lesson, Room, Student, Teacher
from app.models.tenant.enums import WEEKDAYS, AttendanceStatus, LessonStatus
from app.schemas.catalog import RoomSummary
from app.schemas.people import StudentSummary, TeacherSummary
from app.schemas.schedule import (
    CalendarEntry,
    ClassGroupCreate,
    ClassGroupUpdate,
    LessonDetail,
    LessonRef,
    RescheduleChain,
    RescheduleStep,
    UpcomingLesson,
)
from app.schemas.schedule import RosterEntry as RosterEntryOut
from app.services import credits

GROUP_LOAD = (
    selectinload(ClassGroup.room),
    selectinload(ClassGroup.teacher),
    selectinload(ClassGroup.enrollments).selectinload(Enrollment.student),
)
LESSON_LOAD = (
    selectinload(Lesson.teacher),
    selectinload(Lesson.attendances).selectinload(Attendance.student),
)


# ---------- Turmas ----------
def validate_slot(studio: Studio, weekday: int, hour: int) -> None:
    if weekday not in WEEKDAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turmas acontecem apenas de segunda a sexta")
    last_start = studio.close_hour - 1
    if not studio.open_hour <= hour <= last_start:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Horário de início deve estar entre {studio.open_hour}h e {last_start}h "
            f"(aulas de 1h; o estúdio fecha às {studio.close_hour}h)",
        )


def ensure_no_conflict(
    db: Session,
    *,
    room_id: int,
    teacher_id: int,
    weekday: int,
    hour: int,
    from_date: date,
    exclude_id: int | None = None,
) -> None:
    """Duas turmas não podem usar a mesma sala, nem o mesmo professor, no mesmo horário."""
    query = select(ClassGroup).options(selectinload(ClassGroup.room), selectinload(ClassGroup.teacher)).where(
        ClassGroup.weekday == weekday,
        ClassGroup.start_hour == hour,
        or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= from_date),
    )
    if exclude_id is not None:
        query = query.where(ClassGroup.id != exclude_id)
    for other in db.scalars(query):
        if other.room_id == room_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A sala {other.room.name} já está ocupada pela turma {other.display_name}"
            )
        if other.teacher_id == teacher_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{other.teacher.name} já dá a turma {other.display_name} nesse horário",
            )
    # Sessões de serviços avulsos já agendadas também ocupam sala e profissional.
    from app.services.offerings import sessions_blocking_group

    blocking = sessions_blocking_group(
        db, weekday=weekday, hour=hour, from_date=from_date, room_id=room_id, teacher_id=teacher_id
    )
    if blocking is not None:
        what = "A sala" if blocking.room_id == room_id else "O profissional"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{what} tem o serviço {blocking.contract.service_name} agendado em {blocking.date:%d/%m/%Y} nesse horário",
        )


def _active(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} não encontrado(a)")
    if not obj.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} está inativo(a)")
    return obj


def create_group(db: Session, studio: Studio, data: ClassGroupCreate) -> ClassGroup:
    validate_slot(studio, data.weekday, data.start_hour)
    room: Room = _active(db, Room, data.room_id, "Sala")
    _active(db, Teacher, data.teacher_id, "Professor")
    capacity = data.capacity or room.capacity
    if capacity > room.capacity:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Capacidade máxima da sala {room.name} é {room.capacity}")
    start = data.start_date or date.today()
    ensure_no_conflict(
        db, room_id=room.id, teacher_id=data.teacher_id, weekday=data.weekday, hour=data.start_hour, from_date=start
    )
    group = ClassGroup(
        name=data.name,
        room_id=room.id,
        teacher_id=data.teacher_id,
        weekday=data.weekday,
        start_hour=data.start_hour,
        capacity=capacity,
        start_date=start,
    )
    db.add(group)
    db.commit()
    return group


def update_group(db: Session, group: ClassGroup, data: ClassGroupUpdate) -> ClassGroup:
    changes = data.model_dump(exclude_unset=True)
    room_id = changes.get("room_id", group.room_id)
    teacher_id = changes.get("teacher_id", group.teacher_id)
    room: Room = _active(db, Room, room_id, "Sala") if "room_id" in changes else group.room
    if "teacher_id" in changes:
        _active(db, Teacher, teacher_id, "Professor")
    capacity = changes.get("capacity", group.capacity)
    if capacity > room.capacity:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Capacidade máxima da sala {room.name} é {room.capacity}")
    if capacity < group.enrolled_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Capacidade menor que o número de alunos da turma")
    if "room_id" in changes or "teacher_id" in changes:
        ensure_no_conflict(
            db,
            room_id=room_id,
            teacher_id=teacher_id,
            weekday=group.weekday,
            hour=group.start_hour,
            from_date=date.today(),
            exclude_id=group.id,
        )
    old_teacher = group.teacher_id
    for field, value in changes.items():
        setattr(group, field, value)
    if teacher_id != old_teacher:
        # Aulas futuras já registradas passam para o novo professor (exceto substituições pontuais).
        for lesson in db.scalars(
            select(Lesson).where(
                Lesson.class_group_id == group.id, Lesson.date >= date.today(), Lesson.teacher_id == old_teacher
            )
        ):
            lesson.teacher_id = teacher_id
    db.commit()
    return group


def end_group(db: Session, group: ClassGroup, end_date: date) -> None:
    """Encerra a turma e os horários padrão dos alunos nela."""
    if end_date < group.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Data de encerramento anterior ao início da turma")
    group.end_date = end_date
    for enrollment in list(group.enrollments):
        if enrollment.start_date > end_date:
            db.delete(enrollment)
        elif enrollment.end_date is None or enrollment.end_date > end_date:
            enrollment.end_date = end_date
    db.commit()


def load_group(db: Session, group_id: int) -> ClassGroup:
    group = db.scalar(select(ClassGroup).options(*GROUP_LOAD).where(ClassGroup.id == group_id))
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turma não encontrada")
    return group


# ---------- Horário padrão do aluno ----------
def set_schedule(db: Session, student: Student, group_ids: list[int], effective_from: date) -> "ScheduleChange":
    """Define o conjunto de turmas padrão do aluno a partir de uma data (não altera o passado)."""
    if len(set(group_ids)) != len(group_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turma repetida na lista")
    allowance = credits.weekly_allowance(db, student.id)
    if group_ids and allowance == 0:
        if credits.latest_subscription(db, student.id) is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "O plano do aluno não tem recorrência: inclua-o nas aulas como avulso",
            )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno precisa ter um plano para entrar em turmas")
    if len(group_ids) > allowance:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"O plano do aluno permite {allowance} turma(s) por semana"
        )

    groups = [load_group(db, gid) for gid in group_ids]
    slots = set()
    for group in groups:
        if group.end_date is not None and group.end_date < effective_from:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Turma {group.display_name} está encerrada")
        slot = (group.weekday, group.start_hour)
        if slot in slots:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duas turmas no mesmo dia e horário")
        slots.add(slot)

    current = list(
        db.scalars(
            select(Enrollment).where(
                Enrollment.student_id == student.id,
                or_(Enrollment.end_date.is_(None), Enrollment.end_date >= effective_from),
            )
        )
    )
    kept = set()
    change = ScheduleChange(effective_from=effective_from)
    for enrollment in current:
        if enrollment.class_group_id in group_ids:
            kept.add(enrollment.class_group_id)
            continue
        change.removed.append(enrollment.class_group.display_name)
        if enrollment.start_date >= effective_from:
            db.delete(enrollment)
        else:
            enrollment.end_date = effective_from - timedelta(days=1)

    for group in groups:
        if group.id in kept:
            continue
        occupied = sum(1 for e in group.enrollments if e.end_date is None or e.end_date >= effective_from)
        if occupied >= group.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Turma {group.display_name} está lotada")
        db.add(
            Enrollment(
                student_id=student.id, class_group_id=group.id, start_date=max(effective_from, group.start_date)
            )
        )
        change.added.append(group.display_name)
    db.flush()
    return change


@dataclass
class ScheduleChange:
    """O que mudou no horário padrão (para o registro de alterações)."""

    effective_from: date
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)

    def describe(self) -> str:
        parts = []
        if self.removed:
            parts.append("removeu " + ", ".join(self.removed))
        if self.added:
            parts.append("adicionou " + ", ".join(self.added))
        return f"Horário padrão alterado a partir de {self.effective_from:%d/%m/%Y}: " + "; ".join(parts)

    def as_changes(self) -> dict:
        return {"effective_from": self.effective_from.isoformat(), "added": self.added, "removed": self.removed}


def enrollment_history(db: Session, student_id: int) -> list[Enrollment]:
    """Todos os horários padrão do aluno (atuais, futuros e encerrados), mais recentes primeiro."""
    return list(
        db.scalars(
            select(Enrollment)
            .join(Enrollment.class_group)
            .options(
                selectinload(Enrollment.class_group).selectinload(ClassGroup.room),
                selectinload(Enrollment.class_group).selectinload(ClassGroup.teacher),
            )
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.start_date.desc(), ClassGroup.weekday, ClassGroup.start_hour)
        )
    )


def current_enrollments(db: Session, student_id: int) -> list[Enrollment]:
    today = date.today()
    return list(
        db.scalars(
            select(Enrollment)
            .join(Enrollment.class_group)
            .options(
                selectinload(Enrollment.class_group).selectinload(ClassGroup.room),
                selectinload(Enrollment.class_group).selectinload(ClassGroup.teacher),
            )
            .where(Enrollment.student_id == student_id, or_(Enrollment.end_date.is_(None), Enrollment.end_date >= today))
            .order_by(ClassGroup.weekday, ClassGroup.start_hour)
        )
    )


# ---------- Aulas ----------
@dataclass
class Roster:
    student: Student
    status: AttendanceStatus
    is_makeup: bool
    attendance: Attendance | None


def find_lesson(db: Session, group_id: int, day: date) -> Lesson | None:
    return db.scalar(
        select(Lesson).options(*LESSON_LOAD).where(Lesson.class_group_id == group_id, Lesson.date == day)
    )


def get_or_create_lesson(db: Session, group: ClassGroup, day: date) -> Lesson:
    lesson = find_lesson(db, group.id, day)
    if lesson is not None:
        return lesson
    if not group.runs_on(day):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A turma {group.display_name} não tem aula em {day:%d/%m/%Y}")
    lesson = Lesson(class_group_id=group.id, date=day, teacher_id=group.teacher_id)
    db.add(lesson)
    db.flush()
    return lesson


def build_roster(group: ClassGroup, day: date, lesson: Lesson | None) -> list[Roster]:
    """Alunos fixos da turma na data + reposições, com o status da chamada."""
    by_student = {a.student_id: a for a in (lesson.attendances if lesson else [])}
    roster: list[Roster] = []
    for enrollment in group.enrollments:
        if enrollment.active_on(day) and enrollment.student.is_active:
            attendance = by_student.pop(enrollment.student_id, None)
            status_ = attendance.status if attendance else AttendanceStatus.PENDING
            roster.append(Roster(enrollment.student, status_, False, attendance))
    for attendance in by_student.values():  # reposições
        roster.append(Roster(attendance.student, attendance.status, attendance.is_makeup, attendance))
    roster.sort(key=lambda r: r.student.name.lower())
    return roster


def attending(roster: list[Roster]) -> list[Roster]:
    """Quem ocupa vaga na aula (todos menos os reagendados para outra aula)."""
    return [r for r in roster if r.status != AttendanceStatus.RESCHEDULED]


def lesson_status(lesson: Lesson | None, roster: list[Roster]) -> LessonStatus:
    if lesson is not None and lesson.is_cancelled:
        return LessonStatus.CANCELLED
    if lesson is not None and lesson.is_completed:
        return LessonStatus.COMPLETED
    return LessonStatus.CONFIRMED if attending(roster) else LessonStatus.INACTIVE


def lesson_start(group: ClassGroup, day: date) -> datetime:
    return datetime.combine(day, time(group.start_hour))


def has_started(group: ClassGroup, day: date) -> bool:
    return lesson_start(group, day) <= datetime.now()


def _entry(group: ClassGroup, day: date, lesson: Lesson | None, roster: list[Roster]) -> dict:
    teacher = lesson.teacher if lesson else group.teacher
    starts_at = datetime.combine(day, time(group.start_hour))
    count = len(attending(roster))
    return dict(
        class_group_id=group.id,
        class_group_name=group.display_name,
        lesson_id=lesson.id if lesson else None,
        date=day,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        room=RoomSummary.model_validate(group.room),
        teacher=TeacherSummary.model_validate(teacher),
        capacity=group.capacity,
        attendees_count=count,
        available_spots=max(group.capacity - count, 0),
        status=lesson_status(lesson, roster),
        completed_at=lesson.completed_at if lesson else None,
    )


def calendar(
    db: Session, date_from: date, date_to: date, room_id: int | None = None, teacher_id: int | None = None
) -> list[CalendarEntry]:
    if date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_to deve ser igual ou posterior a date_from")
    if (date_to - date_from).days > 62:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Período máximo do calendário é de 62 dias")

    query = select(ClassGroup).options(*GROUP_LOAD).where(
        ClassGroup.start_date <= date_to, or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= date_from)
    )
    if room_id:
        query = query.where(ClassGroup.room_id == room_id)
    groups = list(db.scalars(query))
    lessons = {
        (l.class_group_id, l.date): l
        for l in db.scalars(
            select(Lesson)
            .options(*LESSON_LOAD)
            .where(Lesson.class_group_id.in_([g.id for g in groups]), Lesson.date >= date_from, Lesson.date <= date_to)
        )
    }

    entries: list[CalendarEntry] = []
    day = date_from
    while day <= date_to:
        for group in sorted(groups, key=lambda g: (g.start_hour, g.room.name)):
            if not group.runs_on(day):
                continue
            lesson = lessons.get((group.id, day))
            if teacher_id and (lesson.teacher_id if lesson else group.teacher_id) != teacher_id:
                continue
            entries.append(CalendarEntry(**_entry(group, day, lesson, build_roster(group, day, lesson))))
        day += timedelta(days=1)
    entries.extend(service_calendar(db, date_from, date_to, room_id, teacher_id))
    entries.sort(key=lambda e: (e.starts_at, e.room.name))
    return entries


def service_calendar(
    db: Session, date_from: date, date_to: date, room_id: int | None = None, teacher_id: int | None = None
) -> list[CalendarEntry]:
    """Sessões de serviços avulsos no período, no mesmo formato das aulas."""
    from app.models.tenant import ServiceContract, ServiceSession
    from app.models.tenant.enums import ServiceSessionStatus

    query = (
        select(ServiceSession)
        .options(
            selectinload(ServiceSession.contract).selectinload(ServiceContract.student),
            selectinload(ServiceSession.room),
            selectinload(ServiceSession.teacher),
        )
        .where(
            ServiceSession.date >= date_from,
            ServiceSession.date <= date_to,
            ServiceSession.start_hour.is_not(None),
            ServiceSession.room_id.is_not(None),
        )
    )
    if room_id:
        query = query.where(ServiceSession.room_id == room_id)
    if teacher_id:
        query = query.where(ServiceSession.teacher_id == teacher_id)

    entries = []
    for s in db.scalars(query):
        cancelled = s.status == ServiceSessionStatus.CANCELLED
        status_ = (
            LessonStatus.CANCELLED
            if cancelled
            else LessonStatus.COMPLETED
            if s.is_completed
            else LessonStatus.CONFIRMED
        )
        starts_at = s.starts_at
        entries.append(
            CalendarEntry(
                kind="service",
                class_group_id=None,
                class_group_name=f"{s.contract.service_name} · {s.contract.student.name}",
                service_session_id=s.id,
                student=StudentSummary.model_validate(s.contract.student),
                lesson_id=None,
                date=s.date,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
                room=RoomSummary.model_validate(s.room),
                teacher=TeacherSummary.model_validate(s.teacher),
                capacity=1,
                attendees_count=0 if cancelled else 1,
                available_spots=0,
                status=status_,
                completed_at=s.completed_at,
            )
        )
    return entries


def lesson_ref(attendance: Attendance | None) -> LessonRef | None:
    if attendance is None:
        return None
    lesson = attendance.lesson
    return LessonRef(
        class_group_id=lesson.class_group_id,
        class_group_name=lesson.class_group.display_name,
        date=lesson.date,
        start_hour=lesson.class_group.start_hour,
    )


def upcoming_lessons(db: Session, student_id: int, days: int = 28) -> list[UpcomingLesson]:
    """Próximas aulas em que o aluno está previsto (fixas e reposições) e que ainda não começaram.

    São as aulas que podem ser reagendadas (origem de um reagendamento).
    """
    today = date.today()
    end = today + timedelta(days=days)
    now = datetime.now()
    result: list[UpcomingLesson] = []
    seen: set[tuple[int, date]] = set()

    def add(group: ClassGroup, day: date, is_makeup: bool) -> None:
        if (group.id, day) in seen or lesson_start(group, day) <= now:
            return
        lesson = find_lesson(db, group.id, day)
        if lesson is not None and (lesson.is_cancelled or lesson.is_completed):
            return
        entry = next((r for r in build_roster(group, day, lesson) if r.student.id == student_id), None)
        if entry is None or entry.status != AttendanceStatus.PENDING:
            return
        seen.add((group.id, day))
        result.append(
            UpcomingLesson(
                class_group_id=group.id,
                class_group_name=group.display_name,
                date=day,
                start_hour=group.start_hour,
                room=group.room.name,
                is_makeup=is_makeup,
            )
        )

    enrollments = db.scalars(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.start_date <= end,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= today),
        )
    )
    for enrollment in enrollments:
        group = load_group(db, enrollment.class_group_id)
        day = today
        while day <= end:
            if group.runs_on(day) and enrollment.active_on(day):
                add(group, day, False)
            day += timedelta(days=1)

    makeups = db.scalars(
        select(Attendance)
        .join(Attendance.lesson)
        .where(
            Attendance.student_id == student_id,
            Attendance.is_makeup.is_(True),
            Attendance.status == AttendanceStatus.PENDING,
            Lesson.date >= today,
            Lesson.date <= end,
        )
    )
    for attendance in makeups:
        add(load_group(db, attendance.lesson.class_group_id), attendance.lesson.date, True)

    result.sort(key=lambda u: (u.date, u.start_hour))
    return result


def reschedule_chains(db: Session, student_id: int) -> list[RescheduleChain]:
    """Cada aula do horário padrão que foi reagendada, com todos os reagendamentos até a situação atual."""
    roots = db.scalars(
        select(Attendance)
        .options(selectinload(Attendance.lesson).selectinload(Lesson.class_group).selectinload(ClassGroup.room))
        .where(
            Attendance.student_id == student_id,
            Attendance.status == AttendanceStatus.RESCHEDULED,
            Attendance.makeup_from_id.is_(None),
        )
    )
    chains: list[RescheduleChain] = []
    for root in roots:
        steps: list[RescheduleStep] = []
        current = root
        while current.status == AttendanceStatus.RESCHEDULED and current.makeup_to is not None and len(steps) < 100:
            target = current.makeup_to
            steps.append(
                RescheduleStep(
                    from_lesson=lesson_ref(current),
                    to_lesson=lesson_ref(target),
                    justification=current.justification,
                    rescheduled_at=current.marked_at,
                )
            )
            current = target
        if not steps:
            continue
        chains.append(
            RescheduleChain(
                original_lesson=lesson_ref(root),
                reschedule_count=len(steps),
                steps=steps,
                current_lesson=lesson_ref(current),
                current_status=current.status,
                current_completed=current.lesson.is_completed,
            )
        )
    chains.sort(key=lambda c: (c.original_lesson.date, c.original_lesson.start_hour), reverse=True)
    return chains


def lesson_detail(db: Session, group: ClassGroup, day: date) -> LessonDetail:
    lesson = find_lesson(db, group.id, day)
    if lesson is None and not group.runs_on(day):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"A turma {group.display_name} não tem aula em {day:%d/%m/%Y}")
    roster = build_roster(group, day, lesson)
    students = [
        RosterEntryOut(
            student=StudentSummary.model_validate(r.student),
            status=r.status,
            justification=r.attendance.justification if r.attendance else None,
            is_makeup=r.is_makeup,
            is_drop_in=bool(r.attendance and r.attendance.is_drop_in),
            makeup_from=lesson_ref(r.attendance.makeup_from) if r.attendance else None,
            rescheduled_to=lesson_ref(r.attendance.makeup_to) if r.attendance else None,
            reschedule_count=r.attendance.reschedule_count if r.attendance else 0,
            original_lesson=lesson_ref(r.attendance.original)
            if r.attendance and r.attendance.makeup_from is not None
            else None,
            credits_remaining=credits.credits_remaining(db, r.student.id),
        )
        for r in roster
    ]
    entry = _entry(group, day, lesson, roster)
    return LessonDetail(
        **entry,
        cancel_reason=lesson.cancel_reason if lesson else None,
        notes=lesson.notes if lesson else None,
        completed_by=lesson.completed_by.name if lesson and lesson.completed_by else None,
        can_complete=entry["status"] == LessonStatus.CONFIRMED and has_started(group, day),
        default_teacher=TeacherSummary.model_validate(group.teacher),
        students=students,
    )
