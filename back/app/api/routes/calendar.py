"""Calendário e aulas (ocorrências das turmas por data): detalhes, chamada, reagendamento e cancelamento."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Staff, get_or_404
from app.models.tenant import Teacher
from app.schemas.schedule import (
    AttendanceSubmit,
    CalendarEntry,
    LessonCancel,
    LessonDetail,
    LessonUpdate,
    RescheduleRequest,
)
from app.services import attendance as service
from app.services import schedule

router = APIRouter(tags=["calendar & lessons"])

LESSON_PATH = "/lessons/{class_group_id}/{lesson_date}"


@router.get(
    "/calendar",
    response_model=list[CalendarEntry],
    summary="Aulas por data e hora (padrão: semana atual, seg-sex)",
)
def get_calendar(
    ctx: Staff,
    date_from: date | None = None,
    date_to: date | None = None,
    room_id: int | None = None,
    teacher_id: int | None = None,
):
    if date_from is None:
        today = date.today()
        date_from = today - timedelta(days=today.weekday())
    date_to = date_to or date_from + timedelta(days=4)
    return schedule.calendar(ctx.db, date_from, date_to, room_id, teacher_id)


def _detail(ctx, class_group_id: int, lesson_date: date) -> LessonDetail:
    ctx.db.expire_all()
    return schedule.lesson_detail(ctx.db, schedule.load_group(ctx.db, class_group_id), lesson_date)


@router.get(LESSON_PATH, response_model=LessonDetail, summary="Detalhes da aula: alunos, professor, dia, hora, status")
def get_lesson(class_group_id: int, lesson_date: date, ctx: Staff):
    return _detail(ctx, class_group_id, lesson_date)


@router.patch(LESSON_PATH, response_model=LessonDetail, summary="Professor substituto / observações da aula")
def update_lesson(class_group_id: int, lesson_date: date, data: LessonUpdate, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    lesson = schedule.get_or_create_lesson(ctx.db, group, lesson_date)
    service.ensure_can_manage(ctx, lesson.teacher_id)
    if data.teacher_id is not None:
        teacher = get_or_404(ctx.db, Teacher, data.teacher_id, "Professor")
        if not teacher.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Professor está inativo")
        lesson.teacher_id = teacher.id
    if "notes" in data.model_fields_set:
        lesson.notes = data.notes
    ctx.db.commit()
    return _detail(ctx, class_group_id, lesson_date)


@router.post(
    f"{LESSON_PATH}/attendance",
    response_model=LessonDetail,
    summary="Chamada: marca presença ou falta (debita aulas do plano)",
)
def take_attendance(class_group_id: int, lesson_date: date, data: AttendanceSubmit, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.take_attendance(ctx, group, lesson_date, data.items)
    return _detail(ctx, class_group_id, lesson_date)


@router.post(
    f"{LESSON_PATH}/reschedule",
    response_model=LessonDetail,
    summary="Reagenda o aluno para outra aula (reposição); não altera o horário padrão",
)
def reschedule(class_group_id: int, lesson_date: date, data: RescheduleRequest, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.reschedule(ctx, group, lesson_date, data.student_id, data.target_class_group_id, data.target_date)
    return _detail(ctx, class_group_id, lesson_date)


@router.delete(
    f"{LESSON_PATH}/reschedule/{{student_id}}",
    response_model=LessonDetail,
    summary="Desfaz um reagendamento feito a partir desta aula",
)
def undo_reschedule(class_group_id: int, lesson_date: date, student_id: int, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.undo_reschedule(ctx, group, lesson_date, student_id)
    return _detail(ctx, class_group_id, lesson_date)


@router.post(f"{LESSON_PATH}/cancel", response_model=LessonDetail, summary="Cancela a aula (professor/estúdio)")
def cancel_lesson(class_group_id: int, lesson_date: date, data: LessonCancel, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.cancel_lesson(ctx, group, lesson_date, data.reason)
    return _detail(ctx, class_group_id, lesson_date)


@router.post(f"{LESSON_PATH}/restore", response_model=LessonDetail, summary="Desfaz o cancelamento")
def restore_lesson(class_group_id: int, lesson_date: date, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.restore_lesson(ctx, group, lesson_date)
    return _detail(ctx, class_group_id, lesson_date)
