"""Chamada (presença/falta), reagendamento (reposição) e cancelamento de aulas."""

from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.tenant import Attendance, ClassGroup, Lesson
from app.models.tenant.enums import AttendanceStatus
from app.schemas.schedule import AttendanceItem
from app.services import credits
from app.services.schedule import GROUP_LOAD, attending, build_roster, find_lesson, get_or_create_lesson, load_group


def ensure_can_manage(ctx, lesson_teacher_id: int) -> None:
    """Admin gerencia qualquer aula; professor apenas as que ele dá."""
    if not ctx.is_admin and ctx.user.teacher_id != lesson_teacher_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o professor da aula ou um admin pode fazer isso")


def take_attendance(ctx, group: ClassGroup, day: date, items: list[AttendanceItem]) -> Lesson:
    db: Session = ctx.db
    if day > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não é possível fazer chamada de aula futura")
    lesson = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, lesson.teacher_id)
    if lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula cancelada")

    roster = {r.student.id: r for r in build_roster(group, day, lesson)}
    consuming = credits.consuming_statuses(ctx.studio)
    for item in items:
        entry = roster.get(item.student_id)
        if entry is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Aluno {item.student_id} não faz parte desta aula")
        if entry.status == AttendanceStatus.RESCHEDULED:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{entry.student.name} foi reagendado(a); desfaça o reagendamento antes de marcar a chamada",
            )
        attendance = entry.attendance
        if attendance is None:
            attendance = Attendance(student_id=entry.student.id, student=entry.student)
            lesson.attendances.append(attendance)
        attendance.status = item.status
        attendance.marked_at = datetime.now()
        attendance.marked_by_id = ctx.user.id
        db.flush()
        if item.status in consuming:
            credits.consume_credit(db, attendance, entry.student, day)
        else:
            credits.release_credit(db, attendance)
    db.commit()
    return lesson


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


def reschedule(ctx, group: ClassGroup, day: date, student_id: int, target_group_id: int, target_day: date) -> Lesson:
    """Move o aluno desta aula para outra (reposição). O horário padrão não muda."""
    db: Session = ctx.db
    if target_group_id == group.id and target_day == day:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula de destino é a mesma da origem")
    if target_day < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reposição deve ser hoje ou em data futura")

    origin = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, origin.teacher_id)
    entry = next((r for r in build_roster(group, day, origin) if r.student.id == student_id), None)
    if entry is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno não faz parte desta aula")
    if entry.status != AttendanceStatus.PENDING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Só é possível reagendar aluno cuja chamada ainda não foi feita"
        )

    target_group = load_group(db, target_group_id)
    target = get_or_create_lesson(db, target_group, target_day)
    if target.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A aula de destino está cancelada")
    target_roster = build_roster(target_group, target_day, target)
    if any(r.student.id == student_id for r in target_roster):
        raise HTTPException(status.HTTP_409_CONFLICT, "Aluno já está na aula de destino")
    if len(attending(target_roster)) >= target_group.capacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "A aula de destino está lotada")
    if _student_busy_at(db, student_id, target_day, target_group.start_hour, target_group.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Aluno já tem outra aula nesse dia e horário")

    source = entry.attendance
    if source is None:
        source = Attendance(student_id=student_id, student=entry.student)
        origin.attendances.append(source)
    source.status = AttendanceStatus.RESCHEDULED
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
    db.commit()
    return target


def undo_reschedule(ctx, group: ClassGroup, day: date, student_id: int) -> None:
    db: Session = ctx.db
    lesson = find_lesson(db, group.id, day)
    source = next((a for a in (lesson.attendances if lesson else []) if a.student_id == student_id), None)
    if source is None or source.status != AttendanceStatus.RESCHEDULED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno não foi reagendado a partir desta aula")
    ensure_can_manage(ctx, lesson.teacher_id)

    makeup = source.makeup_to
    if makeup is not None:
        if makeup.status != AttendanceStatus.PENDING:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reposição já teve chamada; não pode ser desfeita")
        makeup.lesson.attendances.remove(makeup)
    if source.is_makeup:
        source.status = AttendanceStatus.PENDING  # volta a ser reposição pendente
    else:
        lesson.attendances.remove(source)  # aluno fixo volta ao estado implícito "pendente"
    db.commit()


def cancel_lesson(ctx, group: ClassGroup, day: date, reason: str | None) -> Lesson:
    db: Session = ctx.db
    lesson = get_or_create_lesson(db, group, day)
    ensure_can_manage(ctx, lesson.teacher_id)
    if lesson.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula já está cancelada")
    if any(a.status in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT) for a in lesson.attendances):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aula já teve chamada; não pode ser cancelada")
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
