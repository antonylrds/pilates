"""Relógio da aplicação no fuso do estúdio (`settings.timezone`).

O servidor roda em UTC, mas "hoje" e "agora" para o usuário são no horário local. Usar `date.today()` ou
`datetime.now()` direto erra o dia entre 21h e meia-noite (UTC-3). Todo código deve usar este módulo.

`now()` devolve um datetime *sem* fuso (horário local de parede), como as colunas de aulas e presenças;
`created_at`/`updated_at` continuam em UTC (`func.now()` do banco) e são convertidos por `local_day_bounds_utc`.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def now() -> datetime:
    """Agora, no horário local, sem fuso."""
    return datetime.now(_tz()).replace(tzinfo=None)


def today() -> date:
    """Hoje, no horário local."""
    return now().date()


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """[início, fim) do dia local `day`, em UTC. Para filtrar colunas gravadas em UTC (`created_at`)."""
    tz = _tz()
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start, end
