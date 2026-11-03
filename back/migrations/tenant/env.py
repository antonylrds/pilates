import app.models.tenant  # noqa: F401  (registra as tabelas)
from app.db.alembic_env import run
from app.db.base import TenantBase

run(TenantBase.metadata, None)
