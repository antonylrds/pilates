"""Finalização de aulas (presença, falta, reagendamento), reposições e cancelamento.

Regra central: presenças e faltas só são registradas quando a aula é **concluída**.
Aulas não concluídas não debitam aulas do plano nem entram no pagamento do professor.
"""

from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.tenant import Attendance, ClassGroup, Lesson, ServiceSession, Student, Teacher
from app.models.tenant.enums import AttendanceStatus, ServiceSessionStatus
from app.schemas.schedule import CompletionItem
from app.services import credits, reports
from app.services.schedule import (
    GROUP_LOAD,
    Roster,
    attending,
    build_roster,
    find_lesson,
    get_or_create_lesson,
    has_started,
    lesson_start,
    load_group,
)


def ensure_can_manage(ctx, lesson_teacher_id: int) -> None:
    """Admin gerencia qualquer aula; professor apenas as que ele dá."""
    if not ctx.is_admin and ctx.user.teacher_id != lesson_teacher_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o professor da aula ou um admin pode fazer isso")


def _ensure_open(lesson: Lesson) -> None:
    if lesson.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula já foi concluída")


def _student_busy_at(db: Session, student_id: int, day: date, hour: int, exclude_group_id: int) -> bool:
    others = db.scalars(
        select(ClassGroup)
        .options(*GROUP_LOAD)
        .where(
            ClassGroup.id != exclude_group_id,
            ClassGroup.weekday == day.weekday(),
            ClassGroup.start_hour == hour,
            ClassGroup.start_date <= day,
            or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= day),
        )
    )
    for other in others:
        roster = attending(build_roster(other, day, find_lesson(db, other.id, day)))
        if any(r.student.id == student_id for r in roster):
            return True
    return False


def _ensure_can_join(db: Session, group: ClassGroup, day: date, lesson: Lesson, student: Student) -> None:
    """Validações comuns para colocar um aluno em uma aula fora do horário padrão."""
    if lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula está cancelada")
    if lesson.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula já foi concluída")
    roster = build_roster(group, day, lesson)
    if any(r.student.id == student.id for r in roster):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{student.name} já está nesta aula")
    if len(attending(roster)) >= group.capacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "A aula está lotada")
    if _student_busy_at(db, student.id, day, group.start_hour, group.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{student.name} já tem outra aula nesse dia e horário")


def _move(
    ctx,
    origin: Lesson,
    entry: Roster,
    target_group_id: int,
    target_day: date,
    justification: str | None,
) -> Attendance:
    """Reagenda o aluno de `origin` para outra aula (sem commit). Não altera o horário padrão."""
    db: Session = ctx.db
    student_id = entry.student.id
    if target_group_id == origin.class_group_id and target_day == origin.date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula de destino é a mesma da origem")

    target_group = load_group(db, target_group_id)
    if lesson_start(target_group, target_day) <= datetime.now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reposição deve ser em uma aula que ainda não começou")
    target = get_or_create_lesson(db, target_group, target_day)
    if target.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula de destino está cancelada")
    if target.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula de destino já foi concluída")
    target_roster = build_roster(target_group, target_day, target)
    if any(r.student.id == student_id for r in target_roster):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{entry.student.name} já está na aula de destino")
    if len(attending(target_roster)) >= target_group.capacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "A aula de destino está lotada")
    if _student_busy_at(db, student_id, target_day, target_group.start_hour, target_group.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{entry.student.name} já tem outra aula nesse dia e horário")

    source = entry.attendance
    if source is None:
        source = Attendance(student_id=student_id, student=entry.student)
        origin.attendances.append(source)
    source.status = AttendanceStatus.RESCHEDULED
    source.justification = justification
    source.marked_at = datetime.now()
    source.marked_by_id = ctx.user.id
    credits.release_credit(db, source)

    makeup = Attendance(
        student_id=student_id,
        student=entry.student,
        status=AttendanceStatus.PENDING,
        is_makeup=True,
        makeup_from=source,
    )
    target.attendances.append(makeup)
    db.flush()
    return makeup


def ensure_teacher_free(db: Session, group: ClassGroup, day: date, teacher: Teacher) -> None:
    """O professor não pode dar outra aula (ou atender um serviço) no mesmo dia e horário."""
    others = db.scalars(
        select(ClassGroup).where(
            ClassGroup.id != group.id,
            ClassGroup.weekday == day.weekday(),
            ClassGroup.start_hour == group.start_hour,
            ClassGroup.start_date <= day,
            or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= day),
        )
    )
    when = f"{day:%d/%m/%Y} às {group.start_hour:02d}h"
    for other in others:
        lesson = find_lesson(db, other.id, day)
        if lesson is not None and lesson.is_cancelled:
            continue
        if (lesson.teacher_id if lesson else other.teacher_id) == teacher.id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{teacher.name} já dá a turma {other.display_name} em {when}")
    session = db.scalar(
        select(ServiceSession).where(
            ServiceSession.date == day,
            ServiceSession.start_hour == group.start_hour,
            ServiceSession.teacher_id == teacher.id,
            ServiceSession.status != ServiceSessionStatus.CANCELLED,
        )
    )
    if session is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{teacher.name} atende {session.contract.service_name} em {when}"
        )


# ---------- Finalização ----------
def complete_lesson(ctx, group: ClassGroup, day: date, items: list[CompletionItem]) -> Lesson:
    """Registra presença/falta/reagendamento de todos os alunos e marca a aula como concluída."""
    db: Session = ctx.db
    lesson = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, lesson.teacher_id)
    if lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula cancelada não pode ser concluída")
    _ensure_open(lesson)
    if not has_started(group, day):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula ainda não começou")

    expected = {r.student.id: r for r in build_roster(group, day, lesson) if r.status != AttendanceStatus.RESCHEDULED}
    if not expected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula sem alunos previstos")

    given: dict[int, CompletionItem] = {}
    for item in items:
        if item.student_id in given:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno repetido na lista")
        if item.student_id not in expected:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Aluno {item.student_id} não está previsto nesta aula")
        given[item.student_id] = item
    missing = [expected[sid].student.name for sid in expected.keys() - given.keys()]
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Informe presença, falta ou reagendamento para: {', '.join(sorted(missing))}"
        )

    consuming = credits.consuming_statuses(ctx.studio)
    now = datetime.now()
    for student_id, item in given.items():
        entry = expected[student_id]
        if item.status == AttendanceStatus.RESCHEDULED:
            _move(ctx, lesson, entry, item.target_class_group_id, item.target_date, item.justification)
            continue
        attendance = entry.attendance
        if attendance is None:
            attendance = Attendance(student_id=student_id, student=entry.student)
            lesson.attendances.append(attendance)
        attendance.status = item.status
        attendance.justification = item.justification if item.status == AttendanceStatus.ABSENT else None
        attendance.marked_at = now
        attendance.marked_by_id = ctx.user.id
        db.flush()
        if item.status in consuming:
            credits.consume_credit(db, attendance, entry.student, day)
        else:
            credits.release_credit(db, attendance)

    db.flush()
    reports.freeze_pay(db, lesson, db.get(Teacher, lesson.teacher_id))
    lesson.completed_at = now
    lesson.completed_by_id = ctx.user.id
    db.commit()
    return lesson


def reopen_lesson(ctx, group: ClassGroup, day: date) -> Lesson:
    """Desfaz a conclusão (somente admin): devolve as aulas debitadas e volta a chamada para pendente."""
    db: Session = ctx.db
    if not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas um admin pode reabrir uma aula concluída")
    lesson = find_lesson(db, group.id, day)
    if lesson is None or not lesson.is_completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula não está concluída")
    for attendance in list(lesson.attendances):
        if attendance.status not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
            continue  # reagendamentos continuam valendo
        credits.release_credit(db, attendance)
        if attendance.is_makeup:
            attendance.status = AttendanceStatus.PENDING
            attendance.justification = None
            attendance.marked_at = None
        else:
            lesson.attendances.remove(attendance)
    lesson.completed_at = None
    lesson.completed_by_id = None
    reports.clear_pay(lesson)
    db.commit()
    return lesson


# ---------- Reagendamento antecipado ----------
def reschedule(
    ctx,
    group: ClassGroup,
    day: date,
    student_id: int,
    target_group_id: int,
    target_day: date,
    justification: str | None = None,
) -> Lesson:
    """Aluno avisa antes da aula: move para outra aula (reposição). O horário padrão não muda."""
    db: Session = ctx.db
    origin = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, origin.teacher_id)
    _ensure_open(origin)
    entry = next((r for r in build_roster(group, day, origin) if r.student.id == student_id), None)
    if entry is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno não faz parte desta aula")
    if entry.status != AttendanceStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno já foi reagendado")
    makeup = _move(ctx, origin, entry, target_group_id, target_day, justification)
    db.commit()
    return makeup.lesson


def undo_reschedule(ctx, group: ClassGroup, day: date, student_id: int) -> None:
    db: Session = ctx.db
    lesson = find_lesson(db, group.id, day)
    source = next((a for a in (lesson.attendances if lesson else []) if a.student_id == student_id), None)
    if source is None or source.status != AttendanceStatus.RESCHEDULED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno não foi reagendado a partir desta aula")
    ensure_can_manage(ctx, lesson.teacher_id)
    _ensure_open(lesson)

    makeup = source.makeup_to
    if makeup is not None:
        if makeup.lesson.is_completed or makeup.status != AttendanceStatus.PENDING:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reposição já foi concluída; não pode ser desfeita")
        makeup.lesson.attendances.remove(makeup)
    if source.is_makeup:
        source.status = AttendanceStatus.PENDING  # volta a ser reposição pendente
        source.justification = None
    else:
        lesson.attendances.remove(source)  # aluno fixo volta ao estado implícito "pendente"
    db.commit()


# ---------- Aula avulsa ----------
def add_drop_in(ctx, group: ClassGroup, day: date, student_id: int, justification: str | None = None) -> Lesson:
    """Inclui o aluno em uma aula sem aula de origem (ex.: plano sem recorrência, aula experimental).

    Não altera o horário padrão. A aula do plano é debitada na conclusão, como qualquer presença.
    """
    db: Session = ctx.db
    student = db.get(Student, student_id)
    if student is None or not student.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aluno não encontrado ou inativo")
    if not group.runs_on(day):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A turma {group.display_name} não tem aula em {day:%d/%m/%Y}")
    if lesson_start(group, day) <= datetime.now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula avulsa deve ser em uma aula que ainda não começou")
    if credits.drop_in_available(db, student_id) <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{student.name} não tem aulas disponíveis no plano para uma aula avulsa"
        )
    lesson = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, lesson.teacher_id)
    _ensure_can_join(db, group, day, lesson, student)
    lesson.attendances.append(
        Attendance(
            student_id=student_id,
            student=student,
            status=AttendanceStatus.PENDING,
            is_makeup=True,
            justification=justification,
        )
    )
    db.commit()
    return lesson


def remove_drop_in(ctx, group: ClassGroup, day: date, student_id: int) -> None:
    db: Session = ctx.db
    lesson = find_lesson(db, group.id, day)
    attendance = next((a for a in (lesson.attendances if lesson else []) if a.student_id == student_id), None)
    if attendance is None or not attendance.is_drop_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno não está nesta aula como avulso")
    ensure_can_manage(ctx, lesson.teacher_id)
    _ensure_open(lesson)
    if attendance.status != AttendanceStatus.PENDING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A aula avulsa já foi reagendada; desfaça o reagendamento antes"
        )
    lesson.attendances.remove(attendance)
    db.commit()


# ---------- Cancelamento ----------
def cancel_lesson(ctx, group: ClassGroup, day: date, reason: str | None) -> Lesson:
    db: Session = ctx.db
    lesson = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, lesson.teacher_id)
    if lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula já está cancelada")
    _ensure_open(lesson)
    lesson.is_cancelled = True
    lesson.cancel_reason = reason
    db.commit()
    return lesson


def restore_lesson(ctx, group: ClassGroup, day: date) -> Lesson:
    db: Session = ctx.db
    lesson = find_lesson(db, group.id, day)
    if lesson is None or not lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula não está cancelada")
    ensure_can_manage(ctx, lesson.teacher_id)
    lesson.is_cancelled = False
    lesson.cancel_reason = None
    db.commit()
    return lesson
