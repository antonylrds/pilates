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


class AttendanceStatus(StrEnum):
    PENDING = "pending"  # aguardando chamada
    PRESENT = "present"
    ABSENT = "absent"
    RESCHEDULED = "rescheduled"  # aluno remarcado para outra aula


class LessonStatus(StrEnum):
    CONFIRMED = "confirmed"  # há alunos previstos
    INACTIVE = "inactive"  # nenhum aluno previsto
    CANCELLED = "cancelled"  # cancelada pelo professor/estúdio


class NotificationKind(StrEnum):
    PLAN_EXHAUSTED = "plan_exhausted"
    NO_CREDITS = "no_credits"


WEEKDAYS = range(0, 5)  # segunda (0) a sexta (4)
WEEKDAY_NAMES = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
LESSON_MINUTES = 60
