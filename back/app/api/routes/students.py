from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import Admin, Staff, apply_update, get_or_404
from app.models.tenant import Attendance, AuditLog, ClassGroup, Enrollment, Lesson, Student, Subscription
from app.models.tenant.enums import AttendanceStatus, SubscriptionStatus
from app.schemas.catalog import SubscriptionCreate, SubscriptionPayment, SubscriptionRead
from app.schemas.people import (
    AuditLogRead,
    ScheduleHistoryItem,
    ScheduleItem,
    ScheduleUpdate,
    StudentCreate,
    StudentDetail,
    StudentRead,
    StudentUpdate,
    UpcomingMakeup,
)
from app.schemas.schedule import LessonRef, RescheduleChain, StudentAttendanceRead, UpcomingLesson
from app.services import audit, credits, payments
from app.services.schedule import (
    current_enrollments,
    enrollment_history,
    reschedule_chains,
    set_schedule,
    upcoming_lessons,
)

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
        drop_in_available=credits.drop_in_available(db, student.id),
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
                reschedule_count=a.reschedule_count,
                original_date=a.original.lesson.date,
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


def _plan_summary(sub: Subscription) -> str:
    paid = f"pago em {audit.fmt_date(sub.paid_at)}" if sub.is_paid and sub.paid_at else "pagamento pendente"
    discount = f", desconto {sub.discount_name}" if sub.discount_name else ""
    return f"{sub.plan_name} ({audit.money(sub.final_price)}{discount}, {paid})"


@router.post(
    "",
    response_model=StudentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra aluno (opcionalmente já com plano, pagamento e turmas padrão)",
)
def create_student(data: StudentCreate, ctx: Admin):
    student = Student(**data.model_dump(exclude={"subscription", "class_group_ids"}))
    ctx.db.add(student)
    ctx.db.flush()
    parts = ["Aluno cadastrado"]
    if data.subscription:
        sub = credits.create_subscription(ctx.db, student, data.subscription)
        parts.append(f"plano {_plan_summary(sub)}")
        if data.class_group_ids:
            change = set_schedule(ctx.db, student, data.class_group_ids, max(sub.start_date, date.today()))
            parts.append("turmas padrão: " + ", ".join(change.added))
    elif data.class_group_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe o plano para definir as turmas")
    audit.log(ctx, student.id, audit.Action.STUDENT_CREATED, "; ".join(parts))
    ctx.db.commit()
    return _detail(ctx, student)


@router.get("/{student_id}", response_model=StudentDetail, summary="Ficha do aluno: contatos, plano, turmas")
def get_student(student_id: int, ctx: Staff):
    return _detail(ctx, _student(ctx, student_id))


@router.patch("/{student_id}", response_model=StudentDetail, summary="Altera os dados do aluno (registra a alteração)")
def update_student(student_id: int, data: StudentUpdate, ctx: Admin):
    student = _student(ctx, student_id)
    changes = audit.diff(student, data.model_dump(exclude_unset=True))
    if changes:
        apply_update(student, data)
        labels = ", ".join(audit.FIELD_LABELS.get(f, f) for f in changes)
        audit.log(ctx, student.id, audit.Action.STUDENT_UPDATED, f"Dados alterados: {labels}", changes)
        ctx.db.commit()
    return _detail(ctx, student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa o aluno e libera as vagas")
def deactivate_student(student_id: int, ctx: Admin):
    student = _student(ctx, student_id)
    student.is_active = False
    change = set_schedule(ctx.db, student, [], date.today())
    description = "Aluno inativado"
    if change.removed:
        description += "; turmas liberadas: " + ", ".join(change.removed)
    audit.log(ctx, student.id, audit.Action.STUDENT_DEACTIVATED, description)
    ctx.db.commit()


@router.post("/{student_id}/reactivate", response_model=StudentDetail)
def reactivate_student(student_id: int, ctx: Admin):
    student = _student(ctx, student_id)
    student.is_active = True
    audit.log(ctx, student.id, audit.Action.STUDENT_REACTIVATED, "Aluno reativado")
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
    summary="Vincula/renova o plano do aluno (com desconto e pagamento opcionais)",
    description="Renovação antecipada: o plano em uso continua sendo debitado até acabar as aulas; "
    "o novo começa a contar em seguida (usage = queued até lá).",
)
def add_subscription(student_id: int, data: SubscriptionCreate, ctx: Admin):
    student = _student(ctx, student_id)
    if not student.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno está inativo")
    in_use = credits.subscription_in_use(ctx.db, student.id)
    subscription = credits.create_subscription(ctx.db, student, data)
    early = " (renovação antecipada)" if in_use is not None else ""
    audit.log(ctx, student.id, audit.Action.PLAN_ADDED, f"Plano contratado{early}: {_plan_summary(subscription)}")
    ctx.db.commit()
    return subscription


def _own_subscription(ctx, student_id: int, subscription_id: int) -> Subscription:
    subscription = get_or_404(ctx.db, Subscription, subscription_id, "Plano do aluno")
    if subscription.student_id != student_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano do aluno não encontrado")
    return subscription


@router.post("/{student_id}/subscriptions/{subscription_id}/cancel", response_model=SubscriptionRead)
def cancel_subscription(student_id: int, subscription_id: int, ctx: Admin):
    subscription = _own_subscription(ctx, student_id, subscription_id)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plano já está cancelado")
    subscription.status = SubscriptionStatus.CANCELLED
    payments.cancel_for_subscription(ctx.db, subscription)
    audit.log(ctx, student_id, audit.Action.PLAN_CANCELLED, f"Plano cancelado: {subscription.plan_name}")
    ctx.db.commit()
    return subscription


@router.patch(
    "/{student_id}/subscriptions/{subscription_id}/payment",
    response_model=SubscriptionRead,
    summary="Marca o plano como pago ou pendente",
)
def update_payment(student_id: int, subscription_id: int, data: SubscriptionPayment, ctx: Admin):
    subscription = _own_subscription(ctx, student_id, subscription_id)
    paid_at = (data.paid_at or date.today()) if data.is_paid else None
    if subscription.is_paid == data.is_paid and subscription.paid_at == paid_at:
        return subscription
    changes = {
        "is_paid": {"from": subscription.is_paid, "to": data.is_paid},
        "paid_at": {
            "from": subscription.paid_at.isoformat() if subscription.paid_at else None,
            "to": paid_at.isoformat() if paid_at else None,
        },
    }
    payments.set_subscription_paid(ctx.db, subscription, data.is_paid, paid_at)
    description = (
        f"Plano {subscription.plan_name} marcado como pago em {audit.fmt_date(paid_at)}"
        if data.is_paid
        else f"Pagamento do plano {subscription.plan_name} marcado como pendente"
    )
    audit.log(ctx, student_id, audit.Action.PAYMENT_UPDATED, description, changes)
    ctx.db.commit()
    ctx.db.refresh(subscription)
    return subscription


# ---------- Horários padrão ----------
@router.get("/{student_id}/schedule", response_model=list[ScheduleItem])
def get_schedule(student_id: int, ctx: Staff):
    return _detail(ctx, _student(ctx, student_id)).schedule


@router.get(
    "/{student_id}/schedule/history",
    response_model=list[ScheduleHistoryItem],
    summary="Histórico de horários padrão (atuais, futuros e encerrados)",
)
def schedule_history(student_id: int, ctx: Staff):
    _student(ctx, student_id)
    today = date.today()

    def status_of(e) -> str:
        if e.start_date > today:
            return "future"
        return "ended" if e.end_date is not None and e.end_date < today else "current"

    return [
        ScheduleHistoryItem(
            enrollment_id=e.id,
            class_group_id=e.class_group_id,
            class_group_name=e.class_group.display_name,
            weekday_name=e.class_group.weekday_name,
            start_hour=e.class_group.start_hour,
            room=e.class_group.room.name,
            teacher=e.class_group.teacher.name,
            start_date=e.start_date,
            end_date=e.end_date,
            status=status_of(e),
        )
        for e in enrollment_history(ctx.db, student_id)
    ]


@router.put(
    "/{student_id}/schedule",
    response_model=StudentDetail,
    summary="Altera as turmas padrão do aluno a partir de uma data (registra a alteração)",
)
def update_schedule(student_id: int, data: ScheduleUpdate, ctx: Admin):
    student = _student(ctx, student_id)
    if not student.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aluno está inativo")
    change = set_schedule(ctx.db, student, data.class_group_ids, data.effective_from or date.today())
    if change.changed:
        audit.log(ctx, student.id, audit.Action.SCHEDULE_CHANGED, change.describe(), change.as_changes())
    ctx.db.commit()
    return _detail(ctx, student)


# ---------- Registro de alterações ----------
@router.get(
    "/{student_id}/history",
    response_model=list[AuditLogRead],
    summary="Registro de alterações do aluno: o que mudou, quem fez e quando",
)
def change_history(student_id: int, ctx: Staff, limit: int = 100):
    _student(ctx, student_id)
    return ctx.db.scalars(
        select(AuditLog)
        .where(AuditLog.student_id == student_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(min(limit, 500))
    ).all()


# ---------- Próximas aulas ----------
@router.get(
    "/{student_id}/upcoming-lessons",
    response_model=list[UpcomingLesson],
    summary="Próximas aulas do aluno que ainda podem ser reagendadas",
)
def student_upcoming_lessons(student_id: int, ctx: Staff, days: int = 28):
    _student(ctx, student_id)
    return upcoming_lessons(ctx.db, student_id, min(max(days, 1), 62))


# ---------- Reagendamentos ----------
@router.get(
    "/{student_id}/reschedules",
    response_model=list[RescheduleChain],
    summary="Acompanhamento dos reagendamentos: cada aula original e quantas vezes foi reagendada",
)
def student_reschedules(student_id: int, ctx: Staff):
    _student(ctx, student_id)
    return reschedule_chains(ctx.db, student_id)


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
            reschedule_count=a.reschedule_count,
            is_makeup=a.is_makeup,
            lesson_completed=a.lesson.is_completed,
            debited=a.subscription_id is not None,
        )
        for a in rows
    ]
