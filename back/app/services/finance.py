"""Caixa do estúdio: recebimentos, faturamento e pagamento dos professores no período.

- Recebimentos e faturamento seguem a **data do pagamento** (`paid_at`) de planos e serviços.
- Pagamento dos professores segue a **data da aula/sessão** finalizada (valores congelados, ver reports).
- A receber: planos e serviços não pagos e não cancelados, de qualquer data.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.tenant import ServiceContract, Subscription
from app.models.tenant.enums import ServiceContractStatus, SubscriptionStatus
from app.schemas.finance import CashPending, CashReceipt, CashReport, CashTeacher
from app.schemas.people import StudentSummary
from app.services.reports import teacher_payments

ZERO = Decimal("0.00")


def _plan_detail(sub: Subscription) -> str | None:
    return f"Desconto: {sub.discount_name}" if sub.discount_name and sub.discount_amount > 0 else None


def _service_detail(contract: ServiceContract) -> str:
    price = f"{contract.price:.2f}".replace(".", ",")
    sessions = f"{contract.occurrences} sessão(ões) × R$ {price}"
    if contract.status == ServiceContractStatus.CANCELLED:
        sessions += " · contratação cancelada"
    return sessions


def cash_report(db: Session, date_from: date, date_to: date) -> CashReport:
    receipts: list[CashReceipt] = []

    subscriptions = db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.student), selectinload(Subscription.plan))
        .where(Subscription.is_paid.is_(True), Subscription.paid_at >= date_from, Subscription.paid_at <= date_to)
    )
    for sub in subscriptions:
        receipts.append(
            CashReceipt(
                kind="plan",
                id=sub.id,
                date=sub.paid_at,
                student=StudentSummary.model_validate(sub.student),
                description=sub.plan_name or sub.plan.name,
                detail=_plan_detail(sub),
                gross=sub.base_price,
                discount=sub.discount_amount,
                amount=sub.final_price,
            )
        )

    contracts = db.scalars(
        select(ServiceContract)
        .options(selectinload(ServiceContract.student), selectinload(ServiceContract.sessions))
        .where(ServiceContract.is_paid.is_(True), ServiceContract.paid_at >= date_from, ServiceContract.paid_at <= date_to)
    )
    for contract in contracts:
        gross = contract.list_price * contract.occurrences
        amount = contract.total_price
        receipts.append(
            CashReceipt(
                kind="service",
                id=contract.id,
                date=contract.paid_at,
                student=StudentSummary.model_validate(contract.student),
                description=contract.service_name,
                detail=_service_detail(contract),
                gross=gross,
                discount=max(gross - amount, ZERO),
                amount=amount,
            )
        )
    receipts.sort(key=lambda r: r.student.name.lower())
    receipts.sort(key=lambda r: r.date, reverse=True)  # mais recentes primeiro; mesmo dia por nome

    # A receber (independe do período)
    pending: list[CashPending] = []
    for sub in db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.student), selectinload(Subscription.plan))
        .where(Subscription.is_paid.is_(False), Subscription.status != SubscriptionStatus.CANCELLED)
    ):
        if sub.final_price <= 0:
            continue  # plano gratuito: nada a receber
        pending.append(
            CashPending(
                kind="plan",
                id=sub.id,
                since=sub.start_date,
                student=StudentSummary.model_validate(sub.student),
                description=sub.plan_name or sub.plan.name,
                amount=sub.final_price,
            )
        )
    for contract in db.scalars(
        select(ServiceContract)
        .options(selectinload(ServiceContract.student), selectinload(ServiceContract.sessions))
        .where(ServiceContract.is_paid.is_(False), ServiceContract.status != ServiceContractStatus.CANCELLED)
    ):
        if contract.total_price <= 0:
            continue
        pending.append(
            CashPending(
                kind="service",
                id=contract.id,
                since=contract.start_date,
                student=StudentSummary.model_validate(contract.student),
                description=contract.service_name,
                amount=contract.total_price,
            )
        )
    pending.sort(key=lambda p: (p.since, p.student.name.lower()))

    pay = teacher_payments(db, date_from, date_to)
    teachers = [
        CashTeacher(
            teacher=t.teacher,
            lessons_given=t.lessons_given,
            lessons_amount=t.lessons_amount,
            services_given=t.services_given,
            services_amount=t.services_amount,
            amount=t.amount,
        )
        for t in pay.teachers
        if t.lessons or t.services
    ]
    teachers.sort(key=lambda t: t.amount, reverse=True)

    plans_total = sum((r.amount for r in receipts if r.kind == "plan"), ZERO)
    services_total = sum((r.amount for r in receipts if r.kind == "service"), ZERO)
    received = plans_total + services_total
    teacher_total = sum((t.amount for t in teachers), ZERO)
    return CashReport(
        date_from=date_from,
        date_to=date_to,
        received_total=received,
        plans_total=plans_total,
        services_total=services_total,
        discounts_total=sum((r.discount for r in receipts), ZERO),
        teacher_payments_total=teacher_total,
        net_total=received - teacher_total,
        pending_total=sum((p.amount for p in pending), ZERO),
        receipts=receipts,
        teachers=teachers,
        pending=pending,
    )
