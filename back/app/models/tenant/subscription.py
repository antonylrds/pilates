from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import SubscriptionStatus

if TYPE_CHECKING:
    from app.models.tenant.catalog import Discount, Plan
    from app.models.tenant.people import Student


class Subscription(TenantBase, TimestampMixin):
    """Plano contratado por um aluno. Preço e quantidade de aulas são congelados na contratação."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    discount_id: Mapped[int | None] = mapped_column(ForeignKey("discounts.id", ondelete="SET NULL"))
    start_date: Mapped[date]
    total_classes: Mapped[int]
    sessions_per_week: Mapped[int]
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    final_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    student: Mapped[Student] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship()
    discount: Mapped[Discount | None] = relationship()

    @property
    def credits_used(self) -> int:
        """Aulas consumidas = chamadas (presença/falta) vinculadas a este plano."""
        from app.models.tenant.schedule import Attendance

        session = object_session(self)
        if session is None or self.id is None:
            return 0
        return session.scalar(select(func.count(Attendance.id)).where(Attendance.subscription_id == self.id)) or 0

    @property
    def credits_remaining(self) -> int:
        return max(self.total_classes - self.credits_used, 0)
