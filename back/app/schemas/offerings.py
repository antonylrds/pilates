from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.tenant.enums import ServiceContractStatus, ServiceRecurrence, ServiceSessionStatus
from app.schemas.catalog import RoomSummary
from app.schemas.common import ORMModel
from app.schemas.people import StudentSummary, TeacherSummary


# ---------- Catálogo ----------
class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2, description="Valor padrão por sessão")


class ServiceUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None


class ServiceRead(ORMModel):
    id: int
    name: str
    description: str | None
    price: Decimal
    is_active: bool
    created_at: datetime


# ---------- Contratação ----------
class ServiceContractCreate(BaseModel):
    service_id: int
    room_id: int = Field(description="Sala ocupada pelas sessões")
    teacher_id: int = Field(description="Profissional que atende")
    start_hour: int = Field(ge=0, le=23, description="Hora de início (sessões de 1h)")
    price: Decimal | None = Field(
        None, ge=0, max_digits=10, decimal_places=2, description="Valor por sessão (padrão: valor do catálogo)"
    )
    recurrence: ServiceRecurrence = Field(ServiceRecurrence.NONE, description="Padrão: sem recorrência")
    occurrences: int | None = Field(None, ge=1, le=52, description="Nº de sessões (recorrente; padrão 4)")
    start_date: date | None = Field(None, description="Data da (primeira) sessão; padrão: hoje")
    is_paid: bool = False
    paid_at: date | None = None
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _occurrences(self):
        if self.recurrence == ServiceRecurrence.NONE:
            if self.occurrences not in (None, 1):
                raise ValueError("Serviço sem recorrência tem uma única sessão")
            self.occurrences = 1
        elif self.occurrences is None:
            self.occurrences = 4
        elif self.occurrences < 2:
            raise ValueError("Serviço recorrente precisa de pelo menos 2 sessões")
        return self


class ServiceContractUpdate(BaseModel):
    """Após a contratação o valor fica congelado; dá para alterar observações e pagamento."""

    notes: str | None = Field(None, max_length=2000)
    is_paid: bool | None = None
    paid_at: date | None = None


class ServiceSessionRead(ORMModel):
    id: int
    date: date
    start_hour: int | None
    room: RoomSummary | None
    teacher: TeacherSummary | None
    status: ServiceSessionStatus
    justification: str | None
    completed_at: datetime | None
    share_percent: Decimal | None = Field(description="% do profissional congelado na finalização")
    teacher_pay: Decimal | None = Field(description="Valor gerado ao profissional (congelado na finalização)")


class ServiceSessionUpdate(BaseModel):
    """Cancela ou reativa uma sessão ainda não finalizada (finalização é por /complete)."""

    status: Literal[ServiceSessionStatus.SCHEDULED, ServiceSessionStatus.CANCELLED]


class ServiceSessionComplete(BaseModel):
    status: Literal["present", "absent"]
    justification: str | None = Field(None, max_length=500, description="Justificativa opcional da falta")


class ServiceContractRead(ORMModel):
    id: int
    student_id: int
    service_id: int
    service_name: str = Field(description="Nome do serviço na contratação")
    list_price: Decimal = Field(description="Valor do catálogo na contratação")
    price: Decimal = Field(description="Valor combinado por sessão")
    price_changed: bool
    total_price: Decimal
    recurrence: ServiceRecurrence
    occurrences: int
    start_date: date
    start_hour: int | None
    room: RoomSummary | None
    teacher: TeacherSummary | None
    status: ServiceContractStatus
    situation: Literal["active", "completed", "cancelled"]
    done_count: int
    next_date: date | None
    is_paid: bool
    paid_at: date | None
    notes: str | None
    created_at: datetime
    sessions: list[ServiceSessionRead]


class ServiceSessionDetail(ServiceSessionRead):
    """Sessão com os dados da contratação (agenda e finalização)."""

    contract_id: int
    service_name: str
    student: StudentSummary
    price: Decimal
    notes: str | None
    can_complete: bool
