"""Criação de bancos e execução de migrações (central e por estúdio)."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.engines import ensure_sqlite_dir
from app.db.roles import ensure_runtime_role, grant_runtime_access

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


def admin_central_url() -> str:
    """URL do banco central com o papel que faz DDL (a das requisições, se não houver papel separado)."""
    return settings.admin_central_database_url or settings.central_database_url


def admin_tenant_url(slug: str) -> str:
    template = settings.admin_tenant_database_url_template or settings.tenant_database_url_template
    return template.format(slug=slug.replace("-", "_"))


def migrate_central() -> None:
    ensure_runtime_role()  # o papel precisa existir antes de receber acesso
    url = admin_central_url()
    ensure_sqlite_dir(url)
    command.upgrade(_alembic_config("central", url), "head")
    grant_runtime_access(url)


def migrate_tenant(slug: str) -> None:
    url = admin_tenant_url(slug)
    command.upgrade(_alembic_config("tenant", url), "head")
    grant_runtime_access(url)


def provision_tenant(slug: str) -> None:
    create_database(admin_tenant_url(slug))
    migrate_tenant(slug)


def _migrate_one(slug: str) -> str | None:
    """Migra um estúdio; devolve a mensagem de erro (ou None se deu certo) em vez de levantar."""
    try:
        migrate_tenant(slug)
        return None
    except Exception as exc:  # um estúdio com problema não pode impedir a migração dos outros
        return f"{type(exc).__name__}: {exc}"


def migrate_tenants(slugs: list[str], jobs: int = 1) -> dict[str, str | None]:
    """Migra os estúdios (em série ou em ``jobs`` processos; o Alembic não é thread-safe) e devolve slug → erro."""
    if jobs <= 1 or len(slugs) <= 1:
        return {slug: _migrate_one(slug) for slug in slugs}
    with ProcessPoolExecutor(max_workers=min(jobs, len(slugs))) as pool:
        return dict(zip(slugs, pool.map(_migrate_one, slugs)))
