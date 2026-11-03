from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.tenant.enums import AttendanceStatus, LessonStatus, NotificationKind
from app.schemas.catalog import RoomSummary
from app.schemas.common import ORMModel
from app.schemas.people import StudentSummary, TeacherSummary


# ---------- Turmas ----------
class ClassGroupCreate(BaseModel):
    name: str | None = Field(None, max_length=120, description="Opcional; padrão: 'Segunda 07h - Sala 1'")
    room_id: int
    teacher_id: int
    weekday: int = Field(ge=0, le=4, description="0 = segunda ... 4 = sexta")
    start_hour: int = Field(ge=0, le=23, description="Hora de início; a aula dura 1h")
    capacity: int | None = Field(None, ge=1, le=50, description="Padrão: capacidade da sala")
    start_date: date | None = Field(None, description="Padrão: hoje")


class ClassGroupUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    room_id: int | None = None
    teacher_id: int | None = None
    capacity: int | None = Field(None, ge=1, le=50)


class ClassGroupRead(ORMModel):
    id: int
    display_name: str
    name: str | None
    weekday: int
    weekday_name: str
    start_hour: int
    end_hour: int
    capacity: int
    room: RoomSummary
    teacher: TeacherSummary
    start_date: date
    end_date: date | None
    enrolled_count: int = 0


class ClassGroupDetail(ClassGroupRead):
    students: list[StudentSummary]


# ---------- Calendário / aulas ----------
class CalendarEntry(BaseModel):
    kind: Literal["lesson", "service"] = Field("lesson", description="Aula de turma ou sessão de serviço avulso")
    class_group_id: int | None = Field(description="Nulo em sessões de serviço")
    class_group_name: str = Field(description="Turma ou 'Serviço · Aluno'")
    service_session_id: int | None = None
    student: StudentSummary | None = Field(None, description="Cliente (sessões de serviço)")
    lesson_id: int | None = Field(description="Nulo enquanto nada foi registrado na aula")
    date: date
    starts_at: datetime
    ends_at: datetime
    room: RoomSummary
    teacher: TeacherSummary
    capacity: int
    attendees_count: int
    available_spots: int
    status: LessonStatus
    completed_at: datetime | None = None


class LessonRef(BaseModel):
    class_group_id: int
    class_group_name: str
    date: date
    start_hour: int


class RosterEntry(BaseModel):
    student: StudentSummary
    status: AttendanceStatus
    justification: str | None = None
    is_makeup: bool = Field(description="Aluno veio por reposição de outra aula")
    makeup_from: LessonRef | None = None
    rescheduled_to: LessonRef | None = None
    reschedule_count: int = Field(0, description="Quantas vezes a aula original deste aluno já foi reagendada")
    original_lesson: LessonRef | None = Field(None, description="Aula original (horário padrão), se for reposição")
    credits_remaining: int


class LessonDetail(CalendarEntry):
    cancel_reason: str | None
    notes: str | None
    completed_by: str | None = None
    can_complete: bool = Field(description="A aula já começou, tem alunos e ainda não foi concluída/cancelada")
    students: list[RosterEntry]


class LessonUpdate(BaseModel):
    teacher_id: int | None = Field(None, description="Professor substituto nesta data")
    notes: str | None = None


class LessonCancel(BaseModel):
    reason: str | None = Field(None, max_length=255)


Justification = Field(None, max_length=500, description="Justificativa opcional")


class CompletionItem(BaseModel):
    """Resultado de um aluno na finalização da aula."""

    student_id: int
    status: Literal[AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.RESCHEDULED]
    justification: str | None = Justification
    target_class_group_id: int | None = Field(None, description="Obrigatório ao reagendar")
    target_date: date | None = Field(None, description="Obrigatório ao reagendar")

    @model_validator(mode="after")
    def _check(self):
        if self.status == AttendanceStatus.RESCHEDULED and (self.target_class_group_id is None or self.target_date is None):
            raise ValueError("Informe a aula de reposição (target_class_group_id e target_date)")
        return self


class LessonComplete(BaseModel):
    items: list[CompletionItem] = Field(description="Um item para cada aluno previsto na aula")


class RescheduleRequest(BaseModel):
    student_id: int
    target_class_group_id: int
    target_date: date
    justification: str | None = Field(None, max_length=500)


class RescheduleStep(BaseModel):
    from_lesson: LessonRef
    to_lesson: LessonRef
    justification: str | None
    rescheduled_at: datetime | None


class RescheduleChain(BaseModel):
    """Acompanhamento dos reagendamentos de uma aula específica do aluno."""

    original_lesson: LessonRef = Field(description="Aula do horário padrão que foi reagendada")
    reschedule_count: int
    steps: list[RescheduleStep]
    current_lesson: LessonRef = Field(description="Onde a aula está agora")
    current_status: AttendanceStatus
    current_completed: bool


class StudentAttendanceRead(BaseModel):
    lesson: LessonRef
    status: AttendanceStatus
    justification: str | None = None
    reschedule_count: int = 0
    is_makeup: bool
    lesson_completed: bool
    debited: bool = Field(description="A aula foi debitada de um plano")


# ---------- Notificações ----------
class NotificationRead(ORMModel):
    id: int
    kind: NotificationKind
    student: StudentSummary
    subscription_id: int | None
    message: str
    is_read: bool
    created_at: datetime


# ---------- Relatório de professores ----------
class PresentStudent(BaseModel):
    id: int
    name: str
    amount: Decimal | None = Field(description="Valor que o aluno gerou ao professor (nulo na regra antiga)")
    plan: str | None = Field(None, description="Plano debitado na aula")


class TeacherLessonReport(BaseModel):
    date: date
    start_hour: int
    class_group_id: int
    class_group_name: str
    room: str
    present_students: list[PresentStudent]
    absent_students: list[StudentSummary]
    amount: Decimal = Field(description="Valor congelado na conclusão da aula")
    minimum_applied: bool = Field(description="O valor da aula foi elevado ao mínimo do professor")
    # Valores do professor vigentes quando a aula foi concluída
    pay_per_class: Decimal
    student_share_percent: Decimal | None = Field(description="Nulo em aulas concluídas na regra anterior")
    min_pay_per_lesson: Decimal


class TeacherServiceReport(BaseModel):
    """Sessão de serviço avulso finalizada pelo profissional."""

    session_id: int
    date: date
    start_hour: int
    service_name: str
    student: StudentSummary
    room: str
    present: bool
    price: Decimal = Field(description="Valor da sessão para o cliente")
    share_percent: Decimal = Field(description="% do profissional na finalização")
    amount: Decimal = Field(description="Valor ao profissional (congelado)")


class TeacherPaymentReport(BaseModel):
    teacher: TeacherSummary
    # Valores atuais do professor (aplicados às próximas aulas/sessões finalizadas)
    pay_per_class: Decimal
    student_share_percent: Decimal
    min_pay_per_lesson: Decimal
    service_share_percent: Decimal
    lessons_given: int = Field(description="Aulas concluídas que geraram pagamento")
    lessons_without_presence: int = Field(description="Dessas, quantas tiveram todos os alunos ausentes")
    total_presences: int
    lessons_amount: Decimal
    services_given: int = Field(description="Sessões de serviço finalizadas com cliente presente")
    services_amount: Decimal
    amount: Decimal = Field(description="Total: aulas + serviços")
    lessons: list[TeacherLessonReport]
    services: list[TeacherServiceReport]


class TeacherPaymentsResponse(BaseModel):
    date_from: date
    date_to: date
    total_amount: Decimal
    teachers: list[TeacherPaymentReport]
