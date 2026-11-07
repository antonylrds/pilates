import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.people import StudentSummary, TeacherSummary

ReceiptKind = Literal["plan", "service"]


class CashReceipt(BaseModel):
    """Um recebimento do estúdio (plano ou serviço avulso pago)."""

    kind: ReceiptKind
    id: int = Field(description="Id da assinatura (plano) ou da contratação (serviço)")
    date: dt.date = Field(description="Data do pagamento")
    student: StudentSummary
    description: str = Field(description="Nome do plano ou do serviço")
    detail: str | None = Field(None, description="Ex.: desconto aplicado, quantidade de sessões")
    gross: Decimal = Field(description="Valor de tabela")
    discount: Decimal = Field(description="Desconto concedido (tabela - pago)")
    amount: Decimal = Field(description="Valor recebido")


class CashPending(BaseModel):
    """Plano ou serviço contratado ainda não pago."""

    kind: ReceiptKind
    id: int
    since: dt.date = Field(description="Início do plano / da primeira sessão")
    student: StudentSummary
    description: str
    amount: Decimal


class CashTeacher(BaseModel):
    """Pagamento devido ao professor no período (aulas e serviços finalizados)."""

    teacher: TeacherSummary
    lessons_given: int
    lessons_amount: Decimal
    services_given: int
    services_amount: Decimal
    amount: Decimal = Field(description="Devido no período (aulas e serviços finalizados)")
    paid: Decimal = Field(description="Já pago no período (pagamentos de professor com status pago)")


class CashTeacherPayment(BaseModel):
    """Pagamento efetivamente feito a um professor (entra como desconto no caixa)."""

    id: int
    date: dt.date = Field(description="Data do pagamento")
    teacher: TeacherSummary
    amount: Decimal
    notes: str | None


class CashReport(BaseModel):
    date_from: dt.date
    date_to: dt.date
    received_total: Decimal = Field(description="Faturamento: tudo o que foi pago no período")
    plans_total: Decimal
    services_total: Decimal
    discounts_total: Decimal = Field(description="Descontos concedidos nos recebimentos do período")
    teacher_payments_total: Decimal = Field(description="Devido aos professores pelas aulas/serviços do período")
    teacher_paid_total: Decimal = Field(description="Pago aos professores no período (desconto do caixa)")
    net_total: Decimal = Field(description="Resultado: faturamento - pago aos professores")
    pending_total: Decimal = Field(description="A receber: planos e serviços em aberto (qualquer data)")
    receipts: list[CashReceipt]
    teachers: list[CashTeacher]
    teacher_payments: list[CashTeacherPayment]
    pending: list[CashPending]
