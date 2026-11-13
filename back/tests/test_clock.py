"""Relógio no fuso do estúdio: "hoje" e o filtro por data de criação não dependem do fuso do servidor."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import update

from app.core import clock
from app.core.config import settings
from app.db.engines import tenant_session
from app.models.tenant import Payment
from tests.conftest import API, LONG_AGO


def test_today_and_now_follow_configured_timezone(monkeypatch):
    for tz in ("America/Sao_Paulo", "Pacific/Kiritimati", "Pacific/Pago_Pago"):
        monkeypatch.setattr(settings, "timezone", tz)
        expected = datetime.now(ZoneInfo(tz))
        assert abs((clock.now() - expected.replace(tzinfo=None)).total_seconds()) < 5
        assert clock.today() in (expected.date(), clock.now().date())
        assert clock.now().tzinfo is None


def test_local_day_bounds_are_utc_instants(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Sao_Paulo")  # UTC-3, sem horário de verão
    start, end = clock.local_day_bounds_utc(date(2026, 11, 12))
    assert start == datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)


def test_created_filter_uses_local_day_late_at_night(client, studio):
    """22h30 em São Paulo já é o dia seguinte em UTC, mas o pagamento pertence ao dia local."""
    plan = studio.plan(price="100.00")
    studio.post("/students", {"name": "Ana", "subscription": {"plan_id": plan["id"], "start_date": LONG_AGO}})
    with tenant_session("alpha") as db:
        db.execute(update(Payment).values(created_at=datetime(2026, 11, 13, 1, 30, tzinfo=timezone.utc)))
        db.commit()

    def count(day: str) -> int:
        r = client.get(f"{API}/payments", params={"date_from": day, "date_to": day}, headers=studio.h)
        assert r.status_code == 200, r.text
        return r.json()["count"]

    assert count("2026-11-12") == 1  # dia local do pagamento
    assert count("2026-11-13") == 0  # o dia UTC não conta
