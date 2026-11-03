from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import SubscriptionStatus, SubscriptionUsage

if TYPE_CHECKING:
    from app.models.tenant.catalog import Discount, Plan
    from app.models.tenant.people import Student


class Subscription(TenantBase, TimestampMixin):
    """Plano contratado por um aluno.

    Nome, preço, desconto e quantidade de aulas são **congelados na contratação**: editar o plano
    ou o desconto depois não altera o histórico. Com vários planos ativos (renovação antecipada),
    as aulas são debitadas do mais antigo até acabar, e só então do seguinte.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    discount_id: Mapped[int | None] = mapped_column(ForeignKey("discounts.id", ondelete="SET NULL"))
    plan_name: Mapped[str | None] = mapped_column(String(120))
    discount_name: Mapped[str | None] = mapped_column(String(120))
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
        """Aulas consumidas = presenças/faltas debitadas deste plano."""
        from app.models.tenant.schedule import Attendance

        session = object_session(self)
        if session is None or self.id is None:
            return 0
        return session.scalar(select(func.count(Attendance.id)).where(Attendance.subscription_id == self.id)) or 0

    @property
    def credits_remaining(self) -> int:
        return max(self.total_classes - self.credits_used, 0)

    @property
    def price_per_lesson(self) -> Decimal:
        if self.total_classes <= 0:
            return Decimal("0.00")
        return (self.final_price / self.total_classes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def usage(self) -> SubscriptionUsage:
        if self.status == SubscriptionStatus.CANCELLED:
            return SubscriptionUsage.CANCELLED
        if self.status == SubscriptionStatus.EXHAUSTED or self.credits_remaining == 0:
            return SubscriptionUsage.FINISHED
        session = object_session(self)
        active = session.scalars(
            select(Subscription)
            .where(Subscription.student_id == self.student_id, Subscription.status == SubscriptionStatus.ACTIVE)
            .order_by(Subscription.start_date, Subscription.id)
        )
        in_use = next((s for s in active if s.credits_remaining > 0), None)
        return SubscriptionUsage.IN_USE if in_use is not None and in_use.id == self.id else SubscriptionUsage.QUEUED

    def _lesson_date(self, fn) -> date | None:
        from app.models.tenant.schedule import Attendance, Lesson

        session = object_session(self)
        if session is None or self.id is None:
            return None
        return session.scalar(
            select(fn(Lesson.date)).join(Attendance.lesson).where(Attendance.subscription_id == self.id)
        )

    @property
    def first_lesson_date(self) -> date | None:
        return self._lesson_date(func.min)

    @property
    def last_lesson_date(self) -> date | None:
        return self._lesson_date(func.max)
