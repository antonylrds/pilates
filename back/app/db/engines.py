"""Engines e sessões: um banco central + um banco por estúdio (tenant)."""

import sqlite3
import threading
import time
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


def _make_engine(url: str, *, central: bool = False) -> Engine:
    if url.startswith("sqlite"):
        ensure_sqlite_dir(url)
        return create_engine(url, connect_args={"check_same_thread": False})
    if central:
        return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, pool_recycle=1800)
    # Pool pequeno por estúdio: poucas conexões ociosas (pool_size) e, em pico, algumas extras que são fechadas ao
    # devolver. Com N estúdios o total ocioso é N × pool_size, por isso os engines ociosos também são descartados.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.tenant_pool_size,
        max_overflow=settings.tenant_pool_max_overflow,
        pool_recycle=1800,
    )


class EngineRegistry:
    """Cache de engines por URL (criação preguiçosa e thread-safe) com descarte de estúdios ociosos.

    O engine do banco central nunca é descartado. Um engine com conexão em uso também não.
    """

    SWEEP_EVERY = 30.0  # segundos entre varreduras

    def __init__(self) -> None:
        self._engines: dict[str, Engine] = {}
        self._last_used: dict[str, float] = {}
        self._last_sweep = time.monotonic()
        self._lock = threading.Lock()

    def get(self, url: str) -> Engine:
        now = time.monotonic()
        engine = self._engines.get(url)
        if engine is None:
            with self._lock:
                engine = self._engines.get(url)
                if engine is None:
                    engine = _make_engine(url, central=url == settings.central_database_url)
                    self._engines[url] = engine
        self._last_used[url] = now
        if now - self._last_sweep >= self.SWEEP_EVERY:
            self.sweep(now)
        return engine

    def sweep(self, now: float | None = None) -> int:
        """Descarta engines ociosos e o excedente de ``tenant_engine_max_cached``. Devolve quantos saíram."""
        now = time.monotonic() if now is None else now
        removed = 0
        with self._lock:
            self._last_sweep = now
            candidates = sorted(
                (url for url in self._engines if url != settings.central_database_url and not self._in_use(url)),
                key=lambda url: self._last_used.get(url, 0.0),
            )  # do menos para o mais recentemente usado
            tenants = len([u for u in self._engines if u != settings.central_database_url])
            for url in candidates:
                idle = now - self._last_used.get(url, 0.0)
                over = tenants > settings.tenant_engine_max_cached
                if idle < settings.tenant_engine_idle_seconds and not over:
                    continue
                self._engines.pop(url).dispose()
                self._last_used.pop(url, None)
                tenants -= 1
                removed += 1
        return removed

    def _in_use(self, url: str) -> bool:
        checkedout = getattr(self._engines[url].pool, "checkedout", None)
        return bool(checkedout and checkedout() > 0)

    def dispose_all(self) -> None:
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()
            self._last_used.clear()


registry = EngineRegistry()


def tenant_url(slug: str) -> str:
    return settings.tenant_database_url_template.format(slug=slug.replace("-", "_"))


def central_session() -> Session:
    return Session(registry.get(settings.central_database_url), expire_on_commit=False)


def tenant_session(slug: str) -> Session:
    return Session(registry.get(tenant_url(slug)), expire_on_commit=False)
