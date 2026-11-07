from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import Admin, get_or_404
from app.models.tenant import Payment
from app.models.tenant.enums import PaymentKind, PaymentStatus
from app.schemas.payments import (
    DateField,
    PaymentCancel,
    PaymentCreate,
    PaymentList,
    PaymentPay,
    PaymentRead,
    PaymentUpdate,
)
from app.services import audit, payments as service

router = APIRouter(prefix="/payments", tags=["payments"])


def _log(ctx, payment: Payment, description: str) -> None:
    """Pagamentos de aluno também entram no registro de alterações da ficha."""
    if payment.student_id is not None:
        audit.log(ctx, payment.student_id, audit.Action.PAYMENT_UPDATED, description,
                  {"payment_id": payment.id, "status": payment.status.value})


def _label(payment: Payment) -> str:
    return f"Pagamento #{payment.id}" + (f" do plano {payment.plan_name}" if payment.plan_name else "")


@router.get(
    "",
    response_model=PaymentList,
    summary="Lista os pagamentos (alunos e professores) com filtros",
    description="`date_from`/`date_to` filtram pela data escolhida em `date_field` (criação, pagamento ou "
    "cancelamento; padrão: criação). Os totais por status consideram todos os pagamentos filtrados.",
)
def list_payments(
    ctx: Admin,
    kind: PaymentKind | None = None,
    student_id: int | None = None,
    teacher_id: int | None = None,
    status_: PaymentStatus | None = Query(None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    date_field: DateField = "created",
    skip: int = 0,
    limit: int = 100,
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_to deve ser igual ou posterior a date_from")
    items, count, totals = service.list_payments(
        ctx.db, kind=kind, student_id=student_id, teacher_id=teacher_id, status_=status_, date_from=date_from,
        date_to=date_to, date_field=date_field, skip=max(skip, 0), limit=min(max(limit, 1), 500),
    )
    return PaymentList(items=items, count=count, totals=totals)


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED, summary="Registra um pagamento")
def create_payment(data: PaymentCreate, ctx: Admin):
    payment = service.create_payment(ctx.db, data)
    _log(ctx, payment, f"{_label(payment)} registrado ({'pago' if data.is_paid else 'pendente'})")
    ctx.db.commit()
    return payment


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(payment_id: int, ctx: Admin):
    return get_or_404(ctx.db, Payment, payment_id, "Pagamento")


@router.patch("/{payment_id}", response_model=PaymentRead, summary="Altera observações, valor (professor) ou data do pagamento")
def update_payment(payment_id: int, data: PaymentUpdate, ctx: Admin):
    payment = get_or_404(ctx.db, Payment, payment_id, "Pagamento")
    fields = data.model_fields_set
    service.update_payment(payment, data.notes, data.amount, data.paid_at, fields)
    _log(ctx, payment, f"{_label(payment)} atualizado")
    ctx.db.commit()
    return payment


@router.post("/{payment_id}/pay", response_model=PaymentRead, summary="Marca como pago")
def pay(payment_id: int, ctx: Admin, data: PaymentPay | None = None):
    payment = get_or_404(ctx.db, Payment, payment_id, "Pagamento")
    service.mark_paid(payment, data.paid_at if data else None)
    _log(ctx, payment, f"{_label(payment)} marcado como pago em {audit.fmt_date(payment.paid_at)}")
    ctx.db.commit()
    return payment


@router.post("/{payment_id}/pending", response_model=PaymentRead, summary="Volta para pendente")
def pending(payment_id: int, ctx: Admin):
    payment = get_or_404(ctx.db, Payment, payment_id, "Pagamento")
    service.mark_pending(payment)
    _log(ctx, payment, f"{_label(payment)} marcado como pendente")
    ctx.db.commit()
    return payment


@router.post("/{payment_id}/cancel", response_model=PaymentRead, summary="Cancela o pagamento")
def cancel(payment_id: int, ctx: Admin, data: PaymentCancel | None = None):
    payment = get_or_404(ctx.db, Payment, payment_id, "Pagamento")
    service.cancel(payment, data.notes if data else None)
    _log(ctx, payment, f"{_label(payment)} cancelado")
    ctx.db.commit()
    return payment
