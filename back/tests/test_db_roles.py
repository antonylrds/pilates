"""Papel das requisições no Postgres: só DML, sem DDL (veja app/db/roles.py).

Precisa de um Postgres de verdade, com um superusuário: defina TEST_POSTGRES_URL, por exemplo
``postgresql+psycopg://postgres:postgres@localhost:5432/postgres`` (o CI sobe um). Sem ela, estes testes são pulados.
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.core.config import settings
from app.db.engines import central_session, registry, tenant_url
from app.db.migrations import create_database, migrate_central, provision_tenant
from app.db.roles import ensure_runtime_role
from app.models.central import PlatformUser
from app.core.security import hash_password
from tests.conftest import API

PG = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG, reason="defina TEST_POSTGRES_URL para testar papéis no Postgres")
pytest.importorskip("psycopg")

APP_PASSWORD = "senha-do-app-123"


class Cluster:
    def __init__(self, prefix: str, role: str):
        self.prefix, self.role = prefix, role
        base = make_url(PG)
        self.admin = base  # superusuário
        self.admin_url = lambda db: base.set(database=db).render_as_string(hide_password=False)
        host = f"{base.host}:{base.port}"
        self.admin_creds = f"{base.username}:{base.password}@{host}"
        self.app_creds = f"{role}:{APP_PASSWORD}@{host}"
        self.central = f"{prefix}central"

    def engine(self, url: str, **kw):
        return create_engine(url, **kw)


@pytest.fixture
def pg(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    c = Cluster(prefix=f"t{suffix}_", role=f"app_{suffix}")
    create_database(c.admin_url(c.central))
    monkeypatch.setattr(settings, "central_database_url", f"postgresql+psycopg://{c.app_creds}/{c.central}")
    monkeypatch.setattr(settings, "admin_central_database_url", f"postgresql+psycopg://{c.admin_creds}/{c.central}")
    monkeypatch.setattr(settings, "tenant_database_url_template", f"postgresql+psycopg://{c.app_creds}/{c.prefix}{{slug}}")
    monkeypatch.setattr(
        settings, "admin_tenant_database_url_template", f"postgresql+psycopg://{c.admin_creds}/{c.prefix}{{slug}}"
    )
    registry.dispose_all()
    yield c
    registry.dispose_all()
    admin = create_engine(c.admin_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for (name,) in conn.execute(text("SELECT datname FROM pg_database WHERE datname LIKE :p"), {"p": f"{c.prefix}%"}):
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'DROP ROLE IF EXISTS "{c.role}"'))
    admin.dispose()


def test_runtime_role_has_no_dangerous_privileges(pg):
    migrate_central()
    admin = pg.engine(pg.admin_url("postgres"))
    with admin.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = :r"), {"r": pg.role}
        ).one()
    admin.dispose()
    assert tuple(row) == (False, False, False)


def test_runtime_role_does_dml_but_not_ddl(pg):
    migrate_central()
    provision_tenant("alfa")
    app = pg.engine(tenant_url("alfa"))
    with app.begin() as conn:
        conn.execute(text("INSERT INTO rooms (name, capacity, is_active) VALUES ('Sala', 3, true)"))
        assert conn.scalar(text("SELECT count(*) FROM rooms")) == 1
        conn.execute(text("UPDATE rooms SET capacity = 4"))
        conn.execute(text("DELETE FROM rooms"))
    for ddl in ("CREATE TABLE intruso (id int)", "DROP TABLE rooms", "ALTER TABLE rooms ADD COLUMN x int", "TRUNCATE rooms"):
        with pytest.raises(ProgrammingError, match="permission denied|must be owner"):
            with app.begin() as conn:
                conn.execute(text(ddl))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with app.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE DATABASE intruso"))
    app.dispose()


def test_tables_created_by_future_migrations_are_accessible(pg):
    migrate_central()
    provision_tenant("alfa")
    admin = pg.engine(pg.admin_url(f"{pg.prefix}alfa"))
    with admin.begin() as conn:  # simula uma migração nova, rodada pelo admin
        conn.execute(text("CREATE TABLE extra (id serial PRIMARY KEY, nome text)"))
    admin.dispose()
    app = pg.engine(tenant_url("alfa"))
    with app.begin() as conn:
        conn.execute(text("INSERT INTO extra (nome) VALUES ('ok')"))  # a sequência serial também foi liberada
        assert conn.scalar(text("SELECT count(*) FROM extra")) == 1
    app.dispose()


def test_ensure_runtime_role_is_idempotent_and_rotates_the_password(pg, monkeypatch):
    assert ensure_runtime_role() is True
    assert ensure_runtime_role() is True
    new = "outra-senha-456"
    monkeypatch.setattr(settings, "central_database_url", f"postgresql+psycopg://{pg.role}:{new}@{make_url(PG).host}:{make_url(PG).port}/{pg.central}")
    ensure_runtime_role()
    migrate_central()
    engine = create_engine(settings.central_database_url)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT 1")) == 1
    engine.dispose()


def test_whole_studio_flow_works_with_the_restricted_role(pg, client):
    """Criação do estúdio (CREATE DATABASE + migração, pelo admin) e uso (pelo papel restrito), via API."""
    migrate_central()
    with central_session() as db:  # papel restrito: INSERT em platform_users
        db.add(PlatformUser(name="Root", email="root@pg.com", hashed_password=hash_password("root-forte-123")))
        db.commit()
    token = client.post(f"{API}/platform/auth/login", json={"email": "root@pg.com", "password": "root-forte-123"}).json()["access_token"]
    body = {"name": "Alfa", "slug": "alfa", "admin_name": "Dona", "admin_email": "dona@alfa.com", "admin_password": "senha-forte-123"}
    r = client.post(f"{API}/platform/studios", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/auth/login", json={"studio": "alfa", "email": "dona@alfa.com", "password": "senha-forte-123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post(f"{API}/rooms", json={"name": "Sala 1", "capacity": 3}, headers=headers).status_code == 201
    assert client.post(f"{API}/students", json={"name": "Ana"}, headers=headers).status_code == 201
