import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.tenant.enums import PaymentKind, PaymentStatus
from app.schemas.common import ORMModel
from app.schemas.people import StudentSummary, TeacherSummary


class PaymentCreate(BaseModel):
    kind: PaymentKind
    amount: Decimal | None = Field(None, ge=0, description="Padrão (aluno): valor pago do plano. Obrigatório para professor")
    is_paid: bool = Field(False, description="Registrar já como pago")
    paid_at: dt.date | None = Field(None, description="Data do pagamento (padrão: hoje, se pago)")
    notes: str | None = Field(None, max_length=2000)
    # aluno
    student_id: int | None = None
    subscription_id: int | None = Field(None, description="Plano do aluno ao qual o pagamento se refere")
    # professor
    teacher_id: int | None = None
    period_start: dt.date | None = None
    period_end: dt.date | None = None

    @model_validator(mode="after")
    def _links(self):
        if self.kind == PaymentKind.STUDENT:
            if self.student_id is None or self.subscription_id is None:
                raise ValueError("Pagamento de aluno exige student_id e subscription_id")
            if self.teacher_id is not None or self.period_start or self.period_end:
                raise ValueError("Pagamento de aluno não tem professor nem período")
        else:
            if self.teacher_id is None:
                raise ValueError("Pagamento de professor exige teacher_id")
            if self.amount is None:
                raise ValueError("Pagamento de professor exige o valor (amount)")
            if self.student_id is not None or self.subscription_id is not None:
                raise ValueError("Pagamento de professor não tem aluno nem plano")
            if self.period_start and self.period_end and self.period_end < self.period_start:
                raise ValueError("period_end deve ser igual ou posterior a period_start")
        return self


class PaymentUpdate(BaseModel):
    """Campos editáveis. O status muda pelas ações pay / pending / cancel."""

    notes: str | None = Field(None, max_length=2000)
    amount: Decimal | None = Field(None, ge=0, description="Só enquanto o pagamento está pendente")
    paid_at: dt.date | None = Field(None, description="Corrige a data de um pagamento já pago")


class PaymentPay(BaseModel):
    paid_at: dt.date | None = Field(None, description="Padrão: hoje")


class PaymentCancel(BaseModel):
    notes: str | None = Field(None, max_length=2000, description="Motivo (substitui as observações, se informado)")


class PaymentRead(ORMModel):
    id: int
    kind: PaymentKind
    status: PaymentStatus
    amount: Decimal
    created_at: dt.datetime = Field(description="Data de criação")
    paid_at: dt.date | None = Field(description="Data do pagamento")
    cancelled_at: dt.date | None = Field(description="Data do cancelamento")
    notes: str | None
    student: StudentSummary | None
    subscription_id: int | None
    plan_name: str | None = Field(description="Plano contratado (pagamento de aluno)")
    teacher: TeacherSummary | None
    period_start: dt.date | None
    period_end: dt.date | None


class PaymentTotals(BaseModel):
    pending: Decimal
    paid: Decimal
    cancelled: Decimal


class PaymentList(BaseModel):
    items: list[PaymentRead]
    count: int = Field(description="Total de pagamentos que atendem aos filtros (ignora skip/limit)")
    totals: PaymentTotals = Field(description="Soma por status dos pagamentos filtrados")


DateField = Literal["created", "paid", "cancelled"]
