from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import Admin, Staff, apply_update, get_or_404
from app.models.tenant import Attendance, ClassGroup, Enrollment, Lesson, Student, Subscription
from app.models.tenant.enums import AttendanceStatus, SubscriptionStatus
from app.schemas.catalog import SubscriptionCreate, SubscriptionRead
from app.schemas.people import (
    ScheduleItem,
    ScheduleUpdate,
    StudentCreate,
    StudentDetail,
    StudentRead,
    StudentUpdate,
    UpcomingMakeup,
)
from app.schemas.schedule import LessonRef, StudentAttendanceRead
from app.services import credits
from app.services.schedule import current_enrollments, set_schedule

router = APIRouter(prefix="/students", tags=["students"])


def _student(ctx, student_id: int) -> Student:
    return get_or_404(ctx.db, Student, student_id, "Aluno")


def _detail(ctx, student: Student) -> StudentDetail:
    db = ctx.db
    subscription = credits.current_subscription(db, student.id)
    remaining = credits.credits_remaining(db, student.id)
    enrollments = current_enrollments(db, student.id)
    schedule = [
        ScheduleItem(
            enrollment_id=e.id,
            class_group_id=e.class_group_id,
            class_group_name=e.class_group.display_name,
            weekday=e.class_group.weekday,
            weekday_name=e.class_group.weekday_name,
            start_hour=e.class_group.start_hour,
            end_hour=e.class_group.end_hour,
            room=e.class_group.room.name,
            teacher=e.class_group.teacher.name,
            start_date=e.start_date,
        )
        for e in enrollments
    ]
    makeups = db.scalars(
        select(Attendance)
        .join(Attendance.lesson)
        .options(selectinload(Attendance.lesson).selectinload(Lesson.class_group).selectinload(ClassGroup.room))
        .where(
            Attendance.student_id == student.id,
            Attendance.is_makeup.is_(True),
            Attendance.status == AttendanceStatus.PENDING,
            Lesson.date >= date.today(),
        )
        .order_by(Lesson.date)
    )
    return StudentDetail(
        **StudentRead.model_validate(student).model_dump(),
        subscription=SubscriptionRead.model_validate(subscription) if subscription else None,
        queued_subscriptions=[
            SubscriptionRead.model_validate(s) for s in credits.queued_subscriptions(db, student.id)
        ],
        credits_remaining=remaining,
        needs_renewal=remaining == 0,
        schedule=schedule,
        free_schedule_slots=max(credits.weekly_allowance(db, student.id) - len(schedule), 0),
        upcoming_makeups=[
            UpcomingMakeup(
                class_group_id=a.lesson.class_group_id,
                class_group_name=a.lesson.class_group.display_name,
                date=a.lesson.date,
                start_hour=a.lesson.class_group.start_hour,
                room=a.lesson.class_group.room.name,
            )
            for a in makeups
        ],
    )


@router.get("", response_model=list[StudentRead])
def list_students(ctx: Staff, q: str | None = None, is_active: bool | None = True, skip: int = 0, limit: int = 100):
    query = select(Student).order_by(Student.name)
    if is_active is not None:
        query = query.where(Student.is_active == is_active)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(Student.name.ilike(like), cast(Student.phones, String).ilike(like), cast(Student.emails, String).ilike(like))
        )
    return ctx.db.scalars(query.offset(skip).limit(min(limit, 500))).all()


@router.post(
    "",
    response_model=StudentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra aluno (opcionalmente já com plano e turmas padrão)",
)
def create_student(data: StudentCreate, ctx: Admin):
    student = Student(**data.model_dump(exclude={"subscription", "class_group_ids"}))
    ctx.db.add(student)
    ctx.db.flush()
    if data.subscription:
        sub = credits.create_subscription(ctx.db, student, data.subscription)
        if data.class_group_ids:
            set_schedule(ctx.db, student, data.class_group_ids, max(sub.start_date, date.today()))
    elif data.class_group_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe o plano para definir as turmas")
    ctx.db.commit()
    return _detail(ctx, student)


@router.get("/{student_id}", response_model=StudentDetail, summary="Ficha do aluno: contatos, plano, turmas")
def get_student(student_id: int, ctx: Staff):
    return _detail(ctx, _student(ctx, student_id))


@router.patch("/{student_id}", response_model=StudentDetail)
def update_student(student_id: int, data: StudentUpdate, ctx: Admin):
    student = _student(ctx, student_id)
    apply_update(student, data)
    ctx.db.commit()
    return _detail(ctx, student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa o aluno e libera as vagas")
def deactivate_student(student_id: int, ctx: Admin):
    student = _student(ctx, student_id)
    student.is_active = False
    set_schedule(ctx.db, student, [], date.today())
    ctx.db.commit()


@router.post("/{student_id}/reactivate", response_model=StudentDetail)
def reactivate_student(student_id: int, ctx: Admin):
    student = _student(ctx, student_id)
    student.is_active = True
    ctx.db.commit()
    return _detail(ctx, student)


# ---------- Plano ----------
@router.get(
    "/{student_id}/subscriptions",
    response_model=list[SubscriptionRead],
    summary="Histórico de planos do aluno (valores congelados da contratação)",
)
def list_subscriptions(student_id: int, ctx: Staff):
    _student(ctx, student_id)
    return ctx.db.scalars(
        select(Subscription)
        .where(Subscription.student_id == student_id)
        .order_by(Subscription.start_date.desc(), Subscription.id.desc())
    ).all()


@router.post(
    "/{student_id}/subscriptions",
    response_model=SubscriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Vincula/renova o plano do aluno (com desconto opcional)",
    description="Renovação antecipada: o plano em uso continua sendo debitado até acabar as aulas; "
    "o novo começa a contar em seguida (usage = queued até lá).",
)
def add_subscription(student_id: int, data: SubscriptionCreate, ctx: Admin):
    student = _student(ctx, student_id)
    if not student.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno está inativo")
    subscription = credits.create_subscription(ctx.db, student, data)
    ctx.db.commit()
    return subscription


@router.post("/{student_id}/subscriptions/{subscription_id}/cancel", response_model=SubscriptionRead)
def cancel_subscription(student_id: int, subscription_id: int, ctx: Admin):
    subscription = get_or_404(ctx.db, Subscription, subscription_id, "Plano do aluno")
    if subscription.student_id != student_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano do aluno não encontrado")
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plano já está cancelado")
    subscription.status = SubscriptionStatus.CANCELLED
    ctx.db.commit()
    return subscription


# ---------- Horários padrão ----------
@router.get("/{student_id}/schedule", response_model=list[ScheduleItem])
def get_schedule(student_id: int, ctx: Staff):
    return _detail(ctx, _student(ctx, student_id)).schedule


@router.put(
    "/{student_id}/schedule",
    response_model=StudentDetail,
    summary="Altera as turmas padrão do aluno a partir de uma data",
)
def update_schedule(student_id: int, data: ScheduleUpdate, ctx: Admin):
    student = _student(ctx, student_id)
    if not student.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno está inativo")
    set_schedule(ctx.db, student, data.class_group_ids, data.effective_from or date.today())
    ctx.db.commit()
    return _detail(ctx, student)


# ---------- Histórico ----------
@router.get("/{student_id}/attendances", response_model=list[StudentAttendanceRead], summary="Histórico de chamadas")
def attendance_history(student_id: int, ctx: Staff, skip: int = 0, limit: int = 50):
    _student(ctx, student_id)
    rows = ctx.db.scalars(
        select(Attendance)
        .join(Attendance.lesson)
        .options(selectinload(Attendance.lesson).selectinload(Lesson.class_group).selectinload(ClassGroup.room))
        .where(Attendance.student_id == student_id)
        .order_by(Lesson.date.desc())
        .offset(skip)
        .limit(min(limit, 200))
    )
    return [
        StudentAttendanceRead(
            lesson=LessonRef(
                class_group_id=a.lesson.class_group_id,
                class_group_name=a.lesson.class_group.display_name,
                date=a.lesson.date,
                start_hour=a.lesson.class_group.start_hour,
            ),
            status=a.status,
            justification=a.justification,
            is_makeup=a.is_makeup,
            lesson_completed=a.lesson.is_completed,
            debited=a.subscription_id is not None,
        )
        for a in rows
    ]
