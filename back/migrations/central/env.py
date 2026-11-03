import app.models.central  # noqa: F401  (registra as tabelas)
from app.core.config import settings
from app.db.alembic_env import run
from app.db.base import CentralBase

run(CentralBase.metadata, settings.central_database_url)
