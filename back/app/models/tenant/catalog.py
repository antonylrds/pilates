from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import DiscountKind


class Room(TenantBase, TimestampMixin):
    """Sala do estúdio."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    capacity: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class Plan(TenantBase, TimestampMixin):
    """Pacote de aulas: frequência semanal + quantidade total de aulas + preço."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    sessions_per_week: Mapped[int]  # 1, 2 ou 3; 0 = sem recorrência (só aulas avulsas)
    total_classes: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True)


class Discount(TenantBase, TimestampMixin):
    """Desconto percentual ou em valor fixo. Sem plan_id vale para qualquer plano."""

    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[DiscountKind] = mapped_column(str_enum(DiscountKind))
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    is_active: Mapped[bool] = mapped_column(default=True)

    plan: Mapped[Plan | None] = relationship()
