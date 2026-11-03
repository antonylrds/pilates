"""Lógica compartilhada pelos env.py de migrations/central e migrations/tenant."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine
from sqlalchemy.pool import NullPool

from app.db.engines import ensure_sqlite_dir


def run(metadata: MetaData, default_url: str | None) -> None:
    config = context.config
    url = (
        config.attributes.get("url")
        or context.get_x_argument(as_dictionary=True).get("url")
        or default_url
    )
    if not url:
        raise RuntimeError("Informe o banco: alembic -n tenant -x url=<database-url> ...")

    if config.config_file_name and not config.attributes.get("embedded"):
        fileConfig(config.config_file_name)

    batch = url.startswith("sqlite")  # ALTER TABLE no SQLite

    if context.is_offline_mode():
        context.configure(url=url, target_metadata=metadata, literal_binds=True, render_as_batch=batch)
        with context.begin_transaction():
            context.run_migrations()
        return

    ensure_sqlite_dir(url)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata, render_as_batch=batch)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
