from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"


class DiscountKind(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXHAUSTED = "exhausted"  # todas as aulas do plano foram usadas
    CANCELLED = "cancelled"


class SubscriptionUsage(StrEnum):
    """Situação do plano no histórico do aluno (calculada)."""

    IN_USE = "in_use"  # plano sendo debitado agora
    QUEUED = "queued"  # renovação antecipada: começa quando o plano em uso acabar
    FINISHED = "finished"  # todas as aulas usadas
    CANCELLED = "cancelled"


class ServiceRecurrence(StrEnum):
    NONE = "none"  # sessão única (padrão)
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class ServiceContractStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class ServiceSessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    DONE = "done"  # finalizada: cliente presente
    MISSED = "missed"  # finalizada: cliente faltou
    CANCELLED = "cancelled"


class AttendanceStatus(StrEnum):
    PENDING = "pending"  # aguardando chamada
    PRESENT = "present"
    ABSENT = "absent"
    RESCHEDULED = "rescheduled"  # aluno remarcado para outra aula


class LessonStatus(StrEnum):
    CONFIRMED = "confirmed"  # há alunos previstos
    INACTIVE = "inactive"  # nenhum aluno previsto
    CANCELLED = "cancelled"  # cancelada pelo professor/estúdio
    COMPLETED = "completed"  # finalizada pelo professor: contabilizada em presenças e pagamentos


class NotificationKind(StrEnum):
    PLAN_EXHAUSTED = "plan_exhausted"
    NO_CREDITS = "no_credits"


WEEKDAYS = range(0, 5)  # segunda (0) a sexta (4)
WEEKDAY_NAMES = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
LESSON_MINUTES = 60
