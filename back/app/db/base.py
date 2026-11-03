from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CentralBase(DeclarativeBase):
    """Tabelas do banco central (registro de estúdios)."""


class TenantBase(DeclarativeBase):
    """Tabelas replicadas no banco de cada estúdio."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Enum salvo como VARCHAR (portável entre SQLite e Postgres)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
