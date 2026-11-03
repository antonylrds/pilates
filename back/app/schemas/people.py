from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.catalog import SubscriptionCreate, SubscriptionRead
from app.schemas.common import EmailList, ORMModel, PhoneList


# ---------- Professores ----------
class TeacherCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phones: PhoneList = []
    emails: EmailList = []
    notes: str | None = None
    pay_per_class: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    pay_per_student: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)


class TeacherUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    phones: PhoneList | None = None
    emails: EmailList | None = None
    notes: str | None = None
    pay_per_class: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    pay_per_student: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None


class TeacherRead(ORMModel):
    id: int
    name: str
    phones: list[str]
    emails: list[str]
    notes: str | None
    pay_per_class: Decimal
    pay_per_student: Decimal
    is_active: bool
    created_at: datetime


class TeacherSummary(ORMModel):
    id: int
    name: str


# ---------- Alunos ----------
class StudentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phones: PhoneList = []
    emails: EmailList = []
    birth_date: date | None = None
    notes: str | None = None
    subscription: SubscriptionCreate | None = Field(None, description="Já vincula um plano no cadastro")
    class_group_ids: list[int] = Field([], description="Turmas padrão (exige plano)")


class StudentUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    phones: PhoneList | None = None
    emails: EmailList | None = None
    birth_date: date | None = None
    notes: str | None = None


class StudentRead(ORMModel):
    id: int
    name: str
    phones: list[str]
    emails: list[str]
    birth_date: date | None
    notes: str | None
    is_active: bool
    created_at: datetime


class StudentSummary(ORMModel):
    id: int
    name: str


class ScheduleItem(BaseModel):
    """Turma padrão do aluno."""

    enrollment_id: int
    class_group_id: int
    class_group_name: str
    weekday: int
    weekday_name: str
    start_hour: int
    end_hour: int
    room: str
    teacher: str
    start_date: date


class UpcomingMakeup(BaseModel):
    class_group_id: int
    class_group_name: str
    date: date
    start_hour: int
    room: str


class StudentDetail(StudentRead):
    subscription: SubscriptionRead | None = Field(description="Plano atual")
    credits_remaining: int = Field(description="Soma das aulas restantes nos planos ativos")
    needs_renewal: bool
    schedule: list[ScheduleItem]
    free_schedule_slots: int = Field(description="Turmas que o plano ainda permite escolher")
    upcoming_makeups: list[UpcomingMakeup]


class ScheduleUpdate(BaseModel):
    class_group_ids: list[int] = Field(description="Conjunto completo de turmas padrão")
    effective_from: date | None = Field(None, description="Data a partir da qual vale o novo horário (padrão: hoje)")
