from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import UserRole

if TYPE_CHECKING:
    from app.models.tenant.schedule import ClassGroup, Enrollment
    from app.models.tenant.subscription import Subscription


class User(TenantBase, TimestampMixin):
    """Usuário que acessa o sistema do estúdio (admin/recepção ou professor)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Usuários com papel "teacher" ficam vinculados ao cadastro de professor.
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"), unique=True)


class Teacher(TenantBase, TimestampMixin):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phones: Mapped[list[str]] = mapped_column(JSON, default=list)
    emails: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    # Remuneração: valor fixo por aula dada + valor por aluno presente.
    pay_per_class: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    pay_per_student: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(default=True)

    class_groups: Mapped[list[ClassGroup]] = relationship(back_populates="teacher")


class Student(TenantBase, TimestampMixin):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    phones: Mapped[list[str]] = mapped_column(JSON, default=list)
    emails: Mapped[list[str]] = mapped_column(JSON, default=list)
    birth_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="student")
