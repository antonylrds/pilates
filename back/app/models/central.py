from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CentralBase, TimestampMixin


class Studio(CentralBase, TimestampMixin):
    """Estúdio (tenant). Cada um tem seu próprio banco de dados."""

    __tablename__ = "studios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))
    # Funcionamento: turmas de 1h começando entre open_hour e close_hour - 1.
    open_hour: Mapped[int] = mapped_column(default=6)
    close_hour: Mapped[int] = mapped_column(default=19)
    # Falta (sem reagendamento) consome uma aula do plano?
    absence_consumes_credit: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class PlatformUser(CentralBase, TimestampMixin):
    """Operador da plataforma: cria e gerencia estúdios."""

    __tablename__ = "platform_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)


class ImpersonationLog(CentralBase):
    """Quando um usuário da plataforma passou a ver um estúdio como outro usuário ("ver como").

    Guarda nomes e o slug junto dos ids para continuar legível se o usuário ou o estúdio mudarem.
    """

    __tablename__ = "impersonation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform_user_id: Mapped[int] = mapped_column(ForeignKey("platform_users.id"), index=True)
    platform_user_name: Mapped[str] = mapped_column(String(120))
    studio_id: Mapped[int] = mapped_column(ForeignKey("studios.id"), index=True)
    studio_slug: Mapped[str] = mapped_column(String(40))
    as_user_id: Mapped[int]
    as_user_name: Mapped[str] = mapped_column(String(120))
    as_role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
