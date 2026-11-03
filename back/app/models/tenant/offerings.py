"""Serviços avulsos (fisioterapia, RPG…): catálogo, contratações dos alunos e sessões."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import ServiceContractStatus, ServiceRecurrence, ServiceSessionStatus

if TYPE_CHECKING:
    from app.models.tenant.catalog import Room
    from app.models.tenant.people import Student, Teacher, User

FINISHED_SESSION = (ServiceSessionStatus.DONE, ServiceSessionStatus.MISSED)


class Service(TenantBase, TimestampMixin):
    """Serviço avulso do catálogo do estúdio, com valor padrão."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True)


class ServiceContract(TenantBase, TimestampMixin):
    """Contratação de um serviço avulso por um aluno.

    Nome e valores ficam congelados: `list_price` é o valor do catálogo na contratação e `price`
    o valor efetivamente combinado por sessão (pode ter sido alterado na contratação).
    Horário, sala e profissional são os padrões das sessões geradas.
    """

    __tablename__ = "service_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"))
    service_name: Mapped[str] = mapped_column(String(120))
    list_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    recurrence: Mapped[ServiceRecurrence] = mapped_column(
        str_enum(ServiceRecurrence), default=ServiceRecurrence.NONE
    )
    occurrences: Mapped[int] = mapped_column(default=1)
    start_date: Mapped[dt.date]
    start_hour: Mapped[int | None]
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"))
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"))
    status: Mapped[ServiceContractStatus] = mapped_column(
        str_enum(ServiceContractStatus), default=ServiceContractStatus.ACTIVE, index=True
    )
    is_paid: Mapped[bool] = mapped_column(default=False, server_default=false())
    paid_at: Mapped[dt.date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    student: Mapped[Student] = relationship()
    service: Mapped[Service] = relationship()
    room: Mapped[Room | None] = relationship()
    teacher: Mapped[Teacher | None] = relationship()
    sessions: Mapped[list[ServiceSession]] = relationship(
        back_populates="contract", cascade="all, delete-orphan", order_by="ServiceSession.date"
    )

    @property
    def total_price(self) -> Decimal:
        return self.price * self.occurrences

    @property
    def price_changed(self) -> bool:
        return self.price != self.list_price

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.sessions if s.status in FINISHED_SESSION)

    @property
    def situation(self) -> str:
        """active (há sessões agendadas) | completed (nenhuma pendente) | cancelled."""
        if self.status == ServiceContractStatus.CANCELLED:
            return "cancelled"
        if any(s.status == ServiceSessionStatus.SCHEDULED for s in self.sessions):
            return "active"
        return "completed"

    @property
    def next_date(self) -> dt.date | None:
        return next((s.date for s in self.sessions if s.status == ServiceSessionStatus.SCHEDULED), None)


class ServiceSession(TenantBase, TimestampMixin):
    """Uma sessão (data, hora, sala, profissional) de um serviço contratado.

    Como as aulas, só conta para o pagamento depois de **finalizada** (presente/falta).
    """

    __tablename__ = "service_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("service_contracts.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    start_hour: Mapped[int | None]
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    status: Mapped[ServiceSessionStatus] = mapped_column(
        str_enum(ServiceSessionStatus), default=ServiceSessionStatus.SCHEDULED
    )
    justification: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[dt.datetime | None]
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Remuneração congelada na finalização: % do profissional e valor gerado.
    share_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    teacher_pay: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    contract: Mapped[ServiceContract] = relationship(back_populates="sessions")
    room: Mapped[Room | None] = relationship()
    teacher: Mapped[Teacher | None] = relationship()
    completed_by: Mapped[User | None] = relationship()

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def starts_at(self) -> dt.datetime | None:
        if self.start_hour is None:
            return None
        return dt.datetime.combine(self.date, dt.time(self.start_hour))
