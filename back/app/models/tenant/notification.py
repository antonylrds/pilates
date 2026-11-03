from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import NotificationKind

if TYPE_CHECKING:
    from app.models.tenant.people import Student


class Notification(TenantBase, TimestampMixin):
    """Aviso para a equipe do estúdio (ex.: aluno precisa renovar o plano)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(default=False, index=True)

    student: Mapped[Student] = relationship()
