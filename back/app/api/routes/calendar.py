"""Calendário e aulas (ocorrências das turmas por data): detalhes, finalização, reagendamento e cancelamento."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Staff, get_or_404
from app.models.tenant import Teacher
from app.models.tenant.enums import LessonStatus
from app.schemas.schedule import (
    CalendarEntry,
    LessonCancel,
    LessonComplete,
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


@router.get(
    "/lessons/pending",
    response_model=list[CalendarEntry],
    summary="Aulas que já começaram e aguardam finalização (professor vê só as suas)",
)
def pending_lessons(ctx: Staff, date_from: date | None = None, date_to: date | None = None):
    today = date.today()
    date_to = min(date_to or today, today)
    date_from = date_from or date_to - timedelta(days=30)
    teacher_id = None
    if not ctx.is_admin:
        teacher_id = ctx.user.teacher_id
        if teacher_id is None:
            return []
    now = datetime.now()
    entries = schedule.calendar(ctx.db, date_from, date_to, teacher_id=teacher_id)
    return [e for e in entries if e.status == LessonStatus.CONFIRMED and e.starts_at <= now]


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
    if data.teacher_id is not None and data.teacher_id != lesson.teacher_id:
        if lesson.is_completed:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Aula concluída: reabra a aula para trocar o professor"
            )
        teacher = get_or_404(ctx.db, Teacher, data.teacher_id, "Professor")
        if not teacher.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Professor está inativo")
        lesson.teacher_id = teacher.id
    if "notes" in data.model_fields_set:
        lesson.notes = data.notes
    ctx.db.commit()
    return _detail(ctx, class_group_id, lesson_date)


@router.post(
    f"{LESSON_PATH}/complete",
    response_model=LessonDetail,
    summary="Finaliza a aula: presença, falta ou reagendamento de cada aluno (com justificativa opcional)",
    description="Todos os alunos previstos devem ser informados. A aula fica 'completed' e passa a contar "
    "em presenças, aulas do plano e pagamento do professor.",
)
def complete_lesson(class_group_id: int, lesson_date: date, data: LessonComplete, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.complete_lesson(ctx, group, lesson_date, data.items)
    return _detail(ctx, class_group_id, lesson_date)


@router.post(
    f"{LESSON_PATH}/reopen",
    response_model=LessonDetail,
    summary="Reabre uma aula concluída (admin) e devolve as aulas debitadas",
)
def reopen_lesson(class_group_id: int, lesson_date: date, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.reopen_lesson(ctx, group, lesson_date)
    return _detail(ctx, class_group_id, lesson_date)


@router.post(
    f"{LESSON_PATH}/reschedule",
    response_model=LessonDetail,
    summary="Reagenda o aluno antes da aula (reposição); não altera o horário padrão",
)
def reschedule(class_group_id: int, lesson_date: date, data: RescheduleRequest, ctx: Staff):
    group = schedule.load_group(ctx.db, class_group_id)
    service.reschedule(
        ctx, group, lesson_date, data.student_id, data.target_class_group_id, data.target_date, data.justification
    )
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
