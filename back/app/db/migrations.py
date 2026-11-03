"""Criação de bancos e execução de migrações (central e por estúdio)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.engines import ensure_sqlite_dir, tenant_url

ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(section: str, url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"), ini_section=section)
    cfg.set_main_option("script_location", str(ROOT / "migrations" / section))
    cfg.attributes["url"] = url
    cfg.attributes["embedded"] = True  # não reconfigura o logging da aplicação
    return cfg


def create_database(url: str) -> None:
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        ensure_sqlite_dir(url)
        return
    if backend == "postgresql":
        admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": parsed.database})
                if not exists:
                    # Nome vem de slug validado (^[a-z0-9_]+$), seguro para interpolar.
                    conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
        finally:
            admin.dispose()
        return
    raise RuntimeError(f"Backend não suportado para provisionamento: {backend}")


def migrate_central() -> None:
    ensure_sqlite_dir(settings.central_database_url)
    command.upgrade(_alembic_config("central", settings.central_database_url), "head")


def migrate_tenant(slug: str) -> None:
    command.upgrade(_alembic_config("tenant", tenant_url(slug)), "head")


def provision_tenant(slug: str) -> None:
    create_database(tenant_url(slug))
    migrate_tenant(slug)
