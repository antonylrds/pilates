"""Pagamentos de alunos (plano) e de professores.

O pagamento de aluno é a fonte da verdade; ``Subscription.is_paid/paid_at`` são um espelho mantido aqui
(o caixa, a visão geral do catálogo e a ficha do aluno continuam lendo esses campos).
"""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.tenant import Payment, Subscription, Teacher
from app.models.tenant.enums import PaymentKind, PaymentStatus
from app.schemas.payments import DateField, PaymentCreate, PaymentTotals

ZERO = Decimal("0.00")


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def _sync_subscription(payment: Payment) -> None:
    sub = payment.subscription
    if payment.kind != PaymentKind.STUDENT or sub is None:
        return
    sub.is_paid = payment.status == PaymentStatus.PAID
    sub.paid_at = payment.paid_at if sub.is_paid else None


def open_payment(db: Session, subscription_id: int) -> Payment | None:
    """Pagamento vigente do plano (o não cancelado mais recente)."""
    return db.scalar(
        select(Payment)
        .where(Payment.subscription_id == subscription_id, Payment.status != PaymentStatus.CANCELLED)
        .order_by(Payment.id.desc())
        .limit(1)
    )


def create_for_subscription(
    db: Session, subscription: Subscription, paid: bool = False, paid_at: date | None = None, notes: str | None = None
) -> Payment:
    """Pagamento do plano recém-vinculado: pendente, ou já pago quando informado."""
    payment = Payment(
        kind=PaymentKind.STUDENT,
        status=PaymentStatus.PAID if paid else PaymentStatus.PENDING,
        amount=subscription.final_price,
        paid_at=(paid_at or date.today()) if paid else None,
        student_id=subscription.student_id,
        subscription_id=subscription.id,
        notes=notes,
    )
    db.add(payment)
    db.flush()
    payment.subscription = subscription
    _sync_subscription(payment)
    return payment


def create_payment(db: Session, data: PaymentCreate) -> Payment:
    if data.kind == PaymentKind.STUDENT:
        sub = db.get(Subscription, data.subscription_id)
        if sub is None or sub.student_id != data.student_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano do aluno não encontrado")
        if data.amount is not None and data.amount != sub.final_price:
            raise _bad("O valor do pagamento de aluno é o valor pago do plano")
        if open_payment(db, sub.id) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Este plano já tem um pagamento ativo")
        if sub.status.value == "cancelled":
            raise _bad("Plano cancelado")
        return create_for_subscription(db, sub, data.is_paid, data.paid_at, data.notes)

    teacher = db.get(Teacher, data.teacher_id)
    if teacher is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professor não encontrado")
    payment = Payment(
        kind=PaymentKind.TEACHER,
        status=PaymentStatus.PAID if data.is_paid else PaymentStatus.PENDING,
        amount=data.amount,
        paid_at=(data.paid_at or date.today()) if data.is_paid else None,
        teacher_id=teacher.id,
        period_start=data.period_start,
        period_end=data.period_end,
        notes=data.notes,
    )
    db.add(payment)
    db.flush()
    return payment


def mark_paid(payment: Payment, paid_at: date | None = None) -> None:
    if payment.status == PaymentStatus.CANCELLED:
        raise _bad("Pagamento cancelado não pode ser pago")
    payment.status = PaymentStatus.PAID
    payment.paid_at = paid_at or payment.paid_at or date.today()
    _sync_subscription(payment)


def mark_pending(payment: Payment) -> None:
    if payment.status == PaymentStatus.CANCELLED:
        raise _bad("Pagamento cancelado não pode voltar a pendente")
    payment.status = PaymentStatus.PENDING
    payment.paid_at = None
    _sync_subscription(payment)


def cancel(payment: Payment, notes: str | None = None) -> None:
    if payment.status == PaymentStatus.CANCELLED:
        raise _bad("Pagamento já está cancelado")
    payment.status = PaymentStatus.CANCELLED
    payment.paid_at = None
    payment.cancelled_at = date.today()
    if notes:
        payment.notes = notes
    _sync_subscription(payment)


def cancel_for_subscription(db: Session, subscription: Subscription) -> None:
    """Plano cancelado: o pagamento ainda pendente deixa de ser devido. Pagamento já feito é mantido."""
    payment = open_payment(db, subscription.id)
    if payment is not None and payment.status == PaymentStatus.PENDING:
        cancel(payment, "Plano cancelado")


def set_subscription_paid(db: Session, subscription: Subscription, paid: bool, paid_at: date | None) -> Payment:
    """Atalho usado pela ficha do aluno (PATCH .../payment): marca o pagamento do plano como pago/pendente."""
    payment = open_payment(db, subscription.id)
    if payment is None:
        payment = create_for_subscription(db, subscription)
    if paid:
        mark_paid(payment, paid_at or date.today())
    else:
        mark_pending(payment)
    return payment


def update_payment(payment: Payment, notes: str | None, amount: Decimal | None, paid_at: date | None, fields: set[str]) -> None:
    if "notes" in fields:
        payment.notes = notes
    if "amount" in fields and amount is not None:
        if payment.kind == PaymentKind.STUDENT:
            raise _bad("O valor do pagamento de aluno é o valor pago do plano")
        if payment.status != PaymentStatus.PENDING:
            raise _bad("O valor só pode ser alterado enquanto o pagamento está pendente")
        payment.amount = amount
    if "paid_at" in fields and paid_at is not None:
        if payment.status != PaymentStatus.PAID:
            raise _bad("A data de pagamento só pode ser alterada em pagamento pago")
        payment.paid_at = paid_at
        _sync_subscription(payment)


def list_payments(
    db: Session,
    *,
    kind: PaymentKind | None,
    student_id: int | None,
    teacher_id: int | None,
    status_: PaymentStatus | None,
    date_from: date | None,
    date_to: date | None,
    date_field: DateField,
    skip: int,
    limit: int,
) -> tuple[list[Payment], int, PaymentTotals]:
    column = {"created": func.date(Payment.created_at), "paid": Payment.paid_at, "cancelled": Payment.cancelled_at}[
        date_field
    ]
    conditions = []
    if kind is not None:
        conditions.append(Payment.kind == kind)
    if student_id is not None:
        conditions.append(Payment.student_id == student_id)
    if teacher_id is not None:
        conditions.append(Payment.teacher_id == teacher_id)
    if status_ is not None:
        conditions.append(Payment.status == status_)
    if date_from is not None:
        conditions.append(column >= date_from)
    if date_to is not None:
        conditions.append(column <= date_to)

    items = list(
        db.scalars(
            select(Payment)
            .options(
                selectinload(Payment.student),
                selectinload(Payment.teacher),
                selectinload(Payment.subscription).selectinload(Subscription.plan),
            )
            .where(*conditions)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .offset(skip)
            .limit(limit)
        )
    )
    count = db.scalar(select(func.count(Payment.id)).where(*conditions)) or 0
    sums = dict(
        db.execute(select(Payment.status, func.coalesce(func.sum(Payment.amount), 0)).where(*conditions).group_by(Payment.status)).all()
    )
    totals = PaymentTotals(
        pending=Decimal(sums.get(PaymentStatus.PENDING, 0)).quantize(ZERO),
        paid=Decimal(sums.get(PaymentStatus.PAID, 0)).quantize(ZERO),
        cancelled=Decimal(sums.get(PaymentStatus.CANCELLED, 0)).quantize(ZERO),
    )
    return items, count, totals
