"""Registro de alterações no cadastro do aluno (o quê, quem e quando)."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.core import clock
from app.models.tenant import AuditLog

FIELD_LABELS = {
    "name": "nome",
    "phones": "telefones",
    "emails": "e-mails",
    "birth_date": "data de nascimento",
    "notes": "observações",
}


class Action:
    STUDENT_CREATED = "student_created"
    STUDENT_UPDATED = "student_updated"
    STUDENT_DEACTIVATED = "student_deactivated"
    STUDENT_REACTIVATED = "student_reactivated"
    SCHEDULE_CHANGED = "schedule_changed"
    PLAN_ADDED = "plan_added"
    PLAN_CANCELLED = "plan_cancelled"
    PAYMENT_UPDATED = "payment_updated"
    SERVICE_CONTRACTED = "service_contracted"
    SERVICE_UPDATED = "service_updated"
    SERVICE_CANCELLED = "service_cancelled"
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_REMOVED = "document_removed"


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def diff(obj: Any, changes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Campos que realmente mudaram: {campo: {"from": antigo, "to": novo}}."""
    result = {}
    for field, new in changes.items():
        old = getattr(obj, field)
        if _plain(old) != _plain(new):
            result[field] = {"from": _plain(old), "to": _plain(new)}
    return result


def log(ctx, student_id: int, action: str, description: str, changes: dict[str, Any] | None = None) -> None:
    ctx.db.add(
        AuditLog(
            student_id=student_id,
            action=action,
            description=description[:500],
            changes=changes,
            user_id=ctx.user.id,
            user_name=ctx.user.name,
            # Horário local do estúdio (D-14); o padrão do banco (CURRENT_TIMESTAMP) seria UTC no SQLite.
            created_at=clock.now(),
        )
    )


def fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def money(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
