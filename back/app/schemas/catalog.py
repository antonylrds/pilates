from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.tenant.enums import DiscountKind, SubscriptionStatus
from app.schemas.common import ORMModel

Money = Field(ge=0, max_digits=10, decimal_places=2)


# ---------- Salas ----------
class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    capacity: int = Field(ge=1, le=50)


class RoomUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    capacity: int | None = Field(None, ge=1, le=50)
    is_active: bool | None = None


class RoomRead(ORMModel):
    id: int
    name: str
    capacity: int
    is_active: bool


class RoomSummary(ORMModel):
    id: int
    name: str


# ---------- Planos ----------
class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    sessions_per_week: int = Field(ge=1, le=3, description="Aulas por semana: 1, 2 ou 3")
    total_classes: int = Field(ge=1, le=500, description="Quantidade de aulas do pacote")
    price: Decimal = Money


class PlanUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    description: str | None = None
    sessions_per_week: int | None = Field(None, ge=1, le=3)
    total_classes: int | None = Field(None, ge=1, le=500)
    price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None


class PlanRead(ORMModel):
    id: int
    name: str
    description: str | None
    sessions_per_week: int
    total_classes: int
    price: Decimal
    is_active: bool
    created_at: datetime


class PlanSummary(ORMModel):
    id: int
    name: str
    sessions_per_week: int
    total_classes: int


# ---------- Descontos ----------
class DiscountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: DiscountKind
    value: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    plan_id: int | None = Field(None, description="Restringe o desconto a um plano; vazio = todos")

    @model_validator(mode="after")
    def _percent(self):
        if self.kind == DiscountKind.PERCENT and self.value > 100:
            raise ValueError("desconto percentual deve ser no máximo 100")
        return self


class DiscountUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    is_active: bool | None = None


class DiscountRead(ORMModel):
    id: int
    name: str
    kind: DiscountKind
    value: Decimal
    plan_id: int | None
    is_active: bool


class DiscountSummary(ORMModel):
    id: int
    name: str
    kind: DiscountKind
    value: Decimal


class PricePreview(BaseModel):
    plan_id: int
    discount_id: int | None
    base_price: Decimal
    discount_amount: Decimal
    final_price: Decimal


# ---------- Plano do aluno ----------
class SubscriptionCreate(BaseModel):
    plan_id: int
    discount_id: int | None = None
    start_date: date | None = Field(None, description="Padrão: hoje")
    notes: str | None = None


class SubscriptionRead(ORMModel):
    id: int
    student_id: int
    plan: PlanSummary
    discount: DiscountSummary | None
    start_date: date
    total_classes: int
    sessions_per_week: int
    base_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    status: SubscriptionStatus
    credits_used: int
    credits_remaining: int
    notes: str | None
    created_at: datetime
