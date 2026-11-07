from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import PaymentKind, PaymentStatus

if TYPE_CHECKING:
    from app.models.tenant.people import Student, Teacher
    from app.models.tenant.subscription import Subscription


class Payment(TenantBase, TimestampMixin):
    """Pagamento do estúdio. O banco já é de um único estúdio, então o vínculo com o estúdio é implícito.

    - ``student``: recebimento de um plano (aluno + plano contratado). Nasce ``pending`` junto com o plano,
      ou ``paid`` quando o plano é contratado já pago. ``Subscription.is_paid/paid_at`` espelham este registro.
    - ``teacher``: repasse a um professor, opcionalmente referente a um período.

    Datas: criação (``created_at``), pagamento (``paid_at``) e cancelamento (``cancelled_at``).
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'student' AND student_id IS NOT NULL AND subscription_id IS NOT NULL AND teacher_id IS NULL)"
            " OR (kind = 'teacher' AND teacher_id IS NOT NULL AND student_id IS NULL AND subscription_id IS NULL)",
            name="ck_payments_kind_links",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[PaymentKind] = mapped_column(str_enum(PaymentKind), index=True)
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    paid_at: Mapped[date | None]
    cancelled_at: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True
    )
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    period_start: Mapped[date | None]  # só repasse a professor
    period_end: Mapped[date | None]

    student: Mapped[Student | None] = relationship()
    subscription: Mapped[Subscription | None] = relationship()
    teacher: Mapped[Teacher | None] = relationship()

    @property
    def plan_name(self) -> str | None:
        sub = self.subscription
        return (sub.plan_name or sub.plan.name) if sub is not None else None
