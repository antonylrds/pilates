"""Serviços avulsos: contratação (com horário, sala e profissional), conflitos de agenda e finalização."""

import calendar
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.central import Studio
from app.models.tenant import ClassGroup, Lesson, Room, Service, ServiceContract, ServiceSession, Student, Teacher
from app.models.tenant.enums import WEEKDAY_NAMES, WEEKDAYS, ServiceContractStatus, ServiceRecurrence, ServiceSessionStatus
from app.schemas.offerings import ServiceContractCreate

RECURRENCE_LABELS = {
    ServiceRecurrence.NONE: "sem recorrência",
    ServiceRecurrence.WEEKLY: "semanal",
    ServiceRecurrence.BIWEEKLY: "quinzenal",
    ServiceRecurrence.MONTHLY: "mensal",
}
CENT = Decimal("0.01")


def add_months(d: date, months: int) -> date:
    """Mesmo dia N meses depois (ajustado ao fim do mês: 31/01 + 1 mês = 28/02)."""
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def session_dates(start: date, recurrence: ServiceRecurrence, occurrences: int) -> list[date]:
    if recurrence == ServiceRecurrence.NONE:
        return [start]
    if recurrence == ServiceRecurrence.MONTHLY:
        return [add_months(start, i) for i in range(occurrences)]
    step = 7 if recurrence == ServiceRecurrence.WEEKLY else 14
    return [start + timedelta(days=step * i) for i in range(occurrences)]


# ---------- Conflitos de agenda (salas e profissionais) ----------
def ensure_slot_free(
    db: Session, day: date, hour: int, room_id: int, teacher_id: int, exclude_session_id: int | None = None
) -> None:
    """Sala e profissional livres no dia/hora: sem turma (aula não cancelada) nem outra sessão de serviço."""
    groups = db.scalars(
        select(ClassGroup).where(
            ClassGroup.weekday == day.weekday(),
            ClassGroup.start_hour == hour,
            ClassGroup.start_date <= day,
            or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= day),
        )
    )
    for group in groups:
        lesson = db.scalar(select(Lesson).where(Lesson.class_group_id == group.id, Lesson.date == day))
        if lesson is not None and lesson.is_cancelled:
            continue
        when = f"{day:%d/%m/%Y} às {hour:02d}h"
        if group.room_id == room_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A sala {group.room.name} está ocupada pela turma {group.display_name} em {when}"
            )
        lesson_teacher = lesson.teacher_id if lesson else group.teacher_id
        if lesson_teacher == teacher_id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"O profissional dá a turma {group.display_name} em {when}")

    query = select(ServiceSession).where(
        ServiceSession.date == day,
        ServiceSession.start_hour == hour,
        ServiceSession.status != ServiceSessionStatus.CANCELLED,
        or_(ServiceSession.room_id == room_id, ServiceSession.teacher_id == teacher_id),
    )
    if exclude_session_id is not None:
        query = query.where(ServiceSession.id != exclude_session_id)
    other = db.scalar(query.limit(1))
    if other is not None:
        what = "A sala" if other.room_id == room_id else "O profissional"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{what} já tem o serviço {other.contract.service_name} em {day:%d/%m/%Y} às {hour:02d}h",
        )


def sessions_blocking_group(
    db: Session, *, weekday: int, hour: int, from_date: date, room_id: int, teacher_id: int
) -> ServiceSession | None:
    """Sessão de serviço futura que impede criar/mover uma turma para esse dia da semana/horário."""
    candidates = db.scalars(
        select(ServiceSession).where(
            ServiceSession.start_hour == hour,
            ServiceSession.date >= from_date,
            ServiceSession.status == ServiceSessionStatus.SCHEDULED,
            or_(ServiceSession.room_id == room_id, ServiceSession.teacher_id == teacher_id),
        )
    )
    return next((s for s in candidates if s.date.weekday() == weekday), None)


def _active(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} não encontrado(a)")
    if not obj.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} está inativo(a)")
    return obj


# ---------- Contratação ----------
def contract_service(db: Session, studio: Studio, student: Student, data: ServiceContractCreate) -> ServiceContract:
    service: Service = _active(db, Service, data.service_id, "Serviço")
    room: Room = _active(db, Room, data.room_id, "Sala")
    _active(db, Teacher, data.teacher_id, "Profissional")
    last_start = studio.close_hour - 1
    if not studio.open_hour <= data.start_hour <= last_start:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Horário deve estar entre {studio.open_hour}h e {last_start}h (sessões de 1h)",
        )
    start = data.start_date or clock.today()
    dates = session_dates(start, data.recurrence, data.occurrences)
    for day in dates:
        if day.weekday() not in WEEKDAYS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"A sessão de {day:%d/%m/%Y} cai em {WEEKDAY_NAMES[day.weekday()].lower()}; o estúdio funciona de segunda a sexta",
            )
        ensure_slot_free(db, day, data.start_hour, room.id, data.teacher_id)

    contract = ServiceContract(
        student_id=student.id,
        service_id=service.id,
        service_name=service.name,
        list_price=service.price,
        price=data.price if data.price is not None else service.price,
        recurrence=data.recurrence,
        occurrences=data.occurrences,
        start_date=start,
        start_hour=data.start_hour,
        room_id=room.id,
        teacher_id=data.teacher_id,
        is_paid=data.is_paid,
        paid_at=(data.paid_at or clock.today()) if data.is_paid else None,
        notes=data.notes,
        sessions=[
            ServiceSession(date=d, start_hour=data.start_hour, room_id=room.id, teacher_id=data.teacher_id)
            for d in dates
        ],
    )
    db.add(contract)
    db.flush()
    return contract


def cancel_contract(contract: ServiceContract) -> int:
    """Cancela a contratação e as sessões agendadas de hoje em diante. Devolve quantas foram canceladas."""
    if contract.status == ServiceContractStatus.CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Serviço já está cancelado")
    contract.status = ServiceContractStatus.CANCELLED
    cancelled = 0
    for session in contract.sessions:
        if session.status == ServiceSessionStatus.SCHEDULED and session.date >= clock.today():
            session.status = ServiceSessionStatus.CANCELLED
            cancelled += 1
    return cancelled


# ---------- Finalização ----------
def ensure_can_manage(ctx, session: ServiceSession) -> None:
    if not ctx.is_admin and ctx.user.teacher_id != session.teacher_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o profissional da sessão ou um admin pode fazer isso")


def has_started(session: ServiceSession) -> bool:
    return session.starts_at is not None and session.starts_at <= clock.now()


def complete_session(ctx, session: ServiceSession, present: bool, justification: str | None) -> None:
    """Finaliza a sessão: presente gera % do valor da sessão ao profissional; falta não gera."""
    ensure_can_manage(ctx, session)
    if session.contract.status == ServiceContractStatus.CANCELLED or session.status == ServiceSessionStatus.CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessão cancelada")
    if session.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A sessão já foi finalizada")
    if not has_started(session):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A sessão ainda não começou")
    teacher = ctx.db.get(Teacher, session.teacher_id)
    session.status = ServiceSessionStatus.DONE if present else ServiceSessionStatus.MISSED
    session.justification = None if present else justification
    session.completed_at = clock.now()
    session.completed_by_id = ctx.user.id
    session.share_percent = teacher.service_share_percent
    session.teacher_pay = (
        (session.contract.price * teacher.service_share_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if present
        else Decimal("0.00")
    )


def reopen_session(ctx, session: ServiceSession) -> None:
    if not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas um admin pode reabrir uma sessão finalizada")
    if not session.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A sessão não está finalizada")
    session.status = ServiceSessionStatus.SCHEDULED
    session.justification = session.completed_at = session.completed_by_id = None
    session.share_percent = session.teacher_pay = None


def session_datetime(session: ServiceSession) -> datetime:
    return datetime.combine(session.date, time(session.start_hour or 0))
