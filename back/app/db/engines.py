"""Engines e sessões: um banco central + um banco por estúdio (tenant)."""

import sqlite3
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import settings


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def ensure_sqlite_dir(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        ensure_sqlite_dir(url)
        return create_engine(url, connect_args={"check_same_thread": False})
    # Pool pequeno por tenant: cada estúdio tem seu próprio pool de conexões.
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=5, pool_recycle=1800)


class EngineRegistry:
    """Cache de engines por URL (criação preguiçosa e thread-safe)."""

    def __init__(self) -> None:
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()

    def get(self, url: str) -> Engine:
        engine = self._engines.get(url)
        if engine is None:
            with self._lock:
                engine = self._engines.get(url)
                if engine is None:
                    engine = _make_engine(url)
                    self._engines[url] = engine
        return engine

    def dispose_all(self) -> None:
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()


registry = EngineRegistry()


def tenant_url(slug: str) -> str:
    return settings.tenant_database_url_template.format(slug=slug.replace("-", "_"))


def central_session() -> Session:
    return Session(registry.get(settings.central_database_url), expire_on_commit=False)


def tenant_session(slug: str) -> Session:
    return Session(registry.get(tenant_url(slug)), expire_on_commit=False)
