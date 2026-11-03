from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantBase, TimestampMixin


class AuditLog(TenantBase, TimestampMixin):
    """Registro de alterações feitas no cadastro do aluno: o quê, quem e quando (created_at).

    O nome do usuário é gravado junto, para continuar legível mesmo se o usuário for removido.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(String(500))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    user_name: Mapped[str] = mapped_column(String(120))
