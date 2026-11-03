"""Planos dos alunos: preço com desconto, consumo de aulas e aviso de renovação."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.central import Studio
from app.models.tenant import Attendance, Discount, Notification, Plan, Student, Subscription
from app.models.tenant.enums import AttendanceStatus, DiscountKind, NotificationKind, SubscriptionStatus
from app.schemas.catalog import SubscriptionCreate

CENT = Decimal("0.01")


def discount_value(price: Decimal, discount: Discount | None) -> Decimal:
    if discount is None:
        return Decimal("0.00")
    amount = price * discount.value / 100 if discount.kind == DiscountKind.PERCENT else discount.value
    return min(amount, price).quantize(CENT, rounding=ROUND_HALF_UP)


def resolve_price(db: Session, plan_id: int, discount_id: int | None) -> tuple[Plan, Discount | None, Decimal]:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano não encontrado")
    if not plan.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plano está inativo")
    discount = None
    if discount_id is not None:
        discount = db.get(Discount, discount_id)
        if discount is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Desconto não encontrado")
        if not discount.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Desconto está inativo")
        if discount.plan_id is not None and discount.plan_id != plan.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Desconto não se aplica a este plano")
    return plan, discount, discount_value(plan.price, discount)


def create_subscription(db: Session, student: Student, data: SubscriptionCreate) -> Subscription:
    plan, discount, disc = resolve_price(db, data.plan_id, data.discount_id)
    subscription = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        discount_id=discount.id if discount else None,
        start_date=data.start_date or date.today(),
        total_classes=plan.total_classes,
        sessions_per_week=plan.sessions_per_week,
        base_price=plan.price,
        discount_amount=disc,
        final_price=plan.price - disc,
        notes=data.notes,
    )
    db.add(subscription)
    db.flush()
    return subscription


def active_subscriptions(db: Session, student_id: int) -> list[Subscription]:
    return list(
        db.scalars(
            select(Subscription)
            .where(Subscription.student_id == student_id, Subscription.status == SubscriptionStatus.ACTIVE)
            .order_by(Subscription.start_date, Subscription.id)
        )
    )


def current_subscription(db: Session, student_id: int) -> Subscription | None:
    """Plano mais recente não cancelado (ativo ou esgotado)."""
    return db.scalar(
        select(Subscription)
        .where(Subscription.student_id == student_id, Subscription.status != SubscriptionStatus.CANCELLED)
        .order_by(Subscription.start_date.desc(), Subscription.id.desc())
        .limit(1)
    )


def credits_remaining(db: Session, student_id: int) -> int:
    return sum(s.credits_remaining for s in active_subscriptions(db, student_id))


def weekly_allowance(db: Session, student_id: int) -> int:
    current = current_subscription(db, student_id)
    return current.sessions_per_week if current else 0


def consuming_statuses(studio: Studio) -> set[AttendanceStatus]:
    statuses = {AttendanceStatus.PRESENT}
    if studio.absence_consumes_credit:
        statuses.add(AttendanceStatus.ABSENT)
    return statuses


def _notify(db: Session, kind: NotificationKind, student: Student, message: str, subscription_id: int | None = None):
    db.add(Notification(kind=kind, student_id=student.id, subscription_id=subscription_id, message=message[:255]))


def consume_credit(db: Session, attendance: Attendance, student: Student, lesson_date: date) -> None:
    """Debita a aula do plano ativo mais antigo com saldo; avisa quando o plano se esgota."""
    if attendance.subscription_id is not None:
        return
    for subscription in active_subscriptions(db, student.id):
        remaining = subscription.credits_remaining
        if remaining <= 0:
            continue
        attendance.subscription_id = subscription.id
        db.flush()
        if remaining == 1:
            subscription.status = SubscriptionStatus.EXHAUSTED
            _notify(
                db,
                NotificationKind.PLAN_EXHAUSTED,
                student,
                f"{student.name} utilizou todas as {subscription.total_classes} aulas do plano "
                f"{subscription.plan.name}. É necessário renovar o plano.",
                subscription.id,
            )
        return

    already_warned = db.scalar(
        select(Notification.id).where(
            Notification.student_id == student.id,
            Notification.kind == NotificationKind.NO_CREDITS,
            Notification.is_read.is_(False),
        )
    )
    if not already_warned:
        _notify(
            db,
            NotificationKind.NO_CREDITS,
            student,
            f"{student.name} teve aula registrada em {lesson_date:%d/%m/%Y} sem aulas disponíveis no plano. "
            "É necessário renovar o plano.",
        )


def release_credit(db: Session, attendance: Attendance) -> None:
    """Devolve a aula ao plano (ex.: chamada corrigida ou aula reagendada)."""
    if attendance.subscription_id is None:
        return
    subscription = attendance.subscription or db.get(Subscription, attendance.subscription_id)
    attendance.subscription_id = None
    db.flush()
    if subscription is not None and subscription.status == SubscriptionStatus.EXHAUSTED:
        subscription.status = SubscriptionStatus.ACTIVE
