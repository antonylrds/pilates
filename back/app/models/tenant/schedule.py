from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBase, TimestampMixin, str_enum
from app.models.tenant.enums import WEEKDAY_NAMES, AttendanceStatus

if TYPE_CHECKING:
    from app.models.tenant.catalog import Room
    from app.models.tenant.people import Student, Teacher, User
    from app.models.tenant.subscription import Subscription


class ClassGroup(TenantBase, TimestampMixin):
    """Turma: horário semanal fixo (dia + hora) em uma sala, com um professor. Dura 1h."""

    __tablename__ = "class_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    weekday: Mapped[int]  # 0 = segunda ... 4 = sexta
    start_hour: Mapped[int]
    capacity: Mapped[int]
    start_date: Mapped[dt.date]
    end_date: Mapped[dt.date | None]  # turma encerrada a partir desta data

    room: Mapped[Room] = relationship()
    teacher: Mapped[Teacher] = relationship(back_populates="class_groups")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="class_group")

    @property
    def display_name(self) -> str:
        return self.name or f"{WEEKDAY_NAMES[self.weekday]} {self.start_hour:02d}h - {self.room.name}"

    @property
    def weekday_name(self) -> str:
        return WEEKDAY_NAMES[self.weekday]

    @property
    def end_hour(self) -> int:
        return self.start_hour + 1

    @property
    def enrolled_count(self) -> int:
        """Alunos fixos atuais ou futuros (ocupam vaga na turma)."""
        today = dt.date.today()
        return sum(1 for e in self.enrollments if e.end_date is None or e.end_date >= today)

    def is_active_on(self, day: dt.date) -> bool:
        return self.start_date <= day and (self.end_date is None or day <= self.end_date)

    def runs_on(self, day: dt.date) -> bool:
        return day.weekday() == self.weekday and self.is_active_on(day)


class Enrollment(TenantBase, TimestampMixin):
    """Horário padrão do aluno: participação fixa em uma turma durante um período."""

    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    class_group_id: Mapped[int] = mapped_column(ForeignKey("class_groups.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[dt.date]
    end_date: Mapped[dt.date | None]

    student: Mapped[Student] = relationship(back_populates="enrollments")
    class_group: Mapped[ClassGroup] = relationship(back_populates="enrollments")

    def active_on(self, day: dt.date) -> bool:
        return self.start_date <= day and (self.end_date is None or day <= self.end_date)


class Lesson(TenantBase, TimestampMixin):
    """Aula: ocorrência de uma turma em uma data.

    Só é gravada quando algo acontece (chamada, reposição, cancelamento, substituição);
    antes disso o calendário a calcula a partir da turma.
    """

    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("class_group_id", "date", name="uq_lesson_group_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    class_group_id: Mapped[int] = mapped_column(ForeignKey("class_groups.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    # Professor que efetivamente dá a aula (permite substituição pontual).
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    is_cancelled: Mapped[bool] = mapped_column(default=False)
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    # Preenchido quando o professor finaliza a aula. Só aulas concluídas contam em presenças e pagamentos.
    completed_at: Mapped[dt.datetime | None] = mapped_column(index=True)
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Remuneração congelada na conclusão (valores do professor naquele momento + valor calculado).
    # student_share_percent é nulo em aulas concluídas antes da regra de percentual do plano.
    pay_per_class: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    student_share_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_pay_per_lesson: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pay_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pay_minimum_applied: Mapped[bool] = mapped_column(default=False, server_default=false())

    class_group: Mapped[ClassGroup] = relationship()
    teacher: Mapped[Teacher] = relationship()
    completed_by: Mapped[User | None] = relationship()
    attendances: Mapped[list[Attendance]] = relationship(back_populates="lesson", cascade="all, delete-orphan")

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None


class Attendance(TenantBase, TimestampMixin):
    """Chamada de um aluno em uma aula: presença, falta ou reagendamento.

    - Alunos fixos da turma só ganham registro quando a chamada é feita ou são reagendados.
    - Reposições (is_makeup) são criadas no reagendamento, apontando para a aula de origem.
    - subscription_id indica de qual plano a aula foi debitada.
    """

    __tablename__ = "attendances"
    __table_args__ = (UniqueConstraint("lesson_id", "student_id", name="uq_attendance_lesson_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    status: Mapped[AttendanceStatus] = mapped_column(str_enum(AttendanceStatus), default=AttendanceStatus.PENDING)
    # Justificativa opcional para falta ou reagendamento.
    justification: Mapped[str | None] = mapped_column(Text)
    is_makeup: Mapped[bool] = mapped_column(default=False)
    makeup_from_id: Mapped[int | None] = mapped_column(ForeignKey("attendances.id", ondelete="SET NULL"))
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )
    # Valor que esta presença gera para o professor (congelado na conclusão da aula).
    teacher_pay: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    marked_at: Mapped[dt.datetime | None]
    marked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    lesson: Mapped[Lesson] = relationship(back_populates="attendances")
    student: Mapped[Student] = relationship()
    subscription: Mapped[Subscription | None] = relationship()
    makeup_from: Mapped[Attendance | None] = relationship(remote_side="Attendance.id", back_populates="makeup_to")
    makeup_to: Mapped[Attendance | None] = relationship(back_populates="makeup_from")
