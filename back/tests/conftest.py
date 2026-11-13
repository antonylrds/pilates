from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.studio_cache import studio_cache
from app.core.security import hash_password
from app.db.engines import central_session, registry
from app.db.migrations import migrate_central
from app.main import app
from app.models.central import PlatformUser

API = "/api/v1"


@pytest.fixture(autouse=True)
def isolated_databases(tmp_path, monkeypatch):
    """Cada teste usa um banco central e bancos de estúdio novos em um diretório temporário."""
    base = tmp_path.as_posix()
    monkeypatch.setattr(settings, "central_database_url", f"sqlite:///{base}/central.db")
    monkeypatch.setattr(settings, "storage_local_root", f"{base}/files")
    monkeypatch.setattr(settings, "tenant_database_url_template", f"sqlite:///{base}/tenant_{{slug}}.db")
    registry.dispose_all()
    limiter.clear()
    studio_cache.invalidate()
    migrate_central()
    with central_session() as db:
        db.add(PlatformUser(name="Root", email="root@test.com", hashed_password=hash_password("root12345")))
        db.commit()
    yield
    registry.dispose_all()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def platform(client):
    r = client.post(f"{API}/platform/auth/login", json={"email": "root@test.com", "password": "root12345"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_studio(client, platform, slug: str, **extra) -> dict[str, str]:
    """Cria o estúdio e devolve os headers do admin dele."""
    body = {
        "name": f"Studio {slug}",
        "slug": slug,
        "admin_name": "Dona",
        "admin_email": f"admin@{slug}.com",
        "admin_password": "secret123",
        **extra,
    }
    r = client.post(f"{API}/platform/studios", json=body, headers=platform)
    assert r.status_code == 201, r.text
    return login(client, slug, f"admin@{slug}.com")


def login(client, slug: str, email: str, password: str = "secret123") -> dict[str, str]:
    r = client.post(f"{API}/auth/login", json={"studio": slug, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client, platform):
    return make_studio(client, platform, "alpha")


# ---------- datas ----------
def past_weekday(weekday: int, weeks_ago: int = 1) -> date:
    """Data passada (antes de hoje) no dia da semana informado."""
    d = clock.today() - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d - timedelta(weeks=weeks_ago - 1)


def future_weekday(weekday: int, weeks_ahead: int = 1) -> date:
    d = clock.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(weeks=weeks_ahead - 1)


LONG_AGO = (clock.today() - timedelta(days=90)).isoformat()


# ---------- montagem de cenário ----------
class Studio:
    """Atalhos para montar dados de teste via API."""

    def __init__(self, client, headers):
        self.c = client
        self.h = headers

    def post(self, path, body, expected=201):
        r = self.c.post(f"{API}{path}", json=body, headers=self.h)
        assert r.status_code == expected, r.text
        return r.json()

    def room(self, name="Sala 1", capacity=3):
        return self.post("/rooms", {"name": name, "capacity": capacity})

    def teacher(self, name="Ana", **extra):
        return self.post("/teachers", {"name": name, **extra})

    def plan(self, sessions_per_week=2, total_classes=8, price="320.00", name=None):
        return self.post(
            "/plans",
            {
                "name": name or f"{sessions_per_week}x semana",
                "sessions_per_week": sessions_per_week,
                "total_classes": total_classes,
                "price": price,
            },
        )

    def group(self, room, teacher, weekday, hour, **extra):
        return self.post(
            "/class-groups",
            {"room_id": room["id"], "teacher_id": teacher["id"], "weekday": weekday, "start_hour": hour,
             "start_date": LONG_AGO, **extra},
        )

    def student(self, name, plan=None, groups=(), **extra):
        body = {"name": name, **extra}
        if plan:
            body["subscription"] = {"plan_id": plan["id"], "start_date": LONG_AGO}
        student = self.post("/students", body)
        if groups:
            r = self.c.put(
                f"{API}/students/{student['id']}/schedule",
                json={"class_group_ids": [g["id"] for g in groups], "effective_from": LONG_AGO},
                headers=self.h,
            )
            assert r.status_code == 200, r.text
            student = r.json()
        return student

    def lesson(self, group, day):
        r = self.c.get(f"{API}/lessons/{group['id']}/{day.isoformat()}", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()

    def complete(self, group, day, items, expected=200, headers=None):
        """Finaliza a aula. items: [(aluno, status)] ou [(aluno, status, extras)]."""
        body = []
        for item in items:
            student, st, *extra = item
            body.append({"student_id": student["id"], "status": st, **(extra[0] if extra else {})})
        r = self.c.post(
            f"{API}/lessons/{group['id']}/{day.isoformat()}/complete",
            json={"items": body},
            headers=headers or self.h,
        )
        assert r.status_code == expected, r.text
        return r.json()

    def credits(self, student):
        return self.c.get(f"{API}/students/{student['id']}", headers=self.h).json()["credits_remaining"]


@pytest.fixture
def studio(client, admin):
    return Studio(client, admin)
