from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    app_name: str = "Pilates Studio API"
    api_prefix: str = "/api/v1"
    # Fuso dos estúdios: define "hoje" e "agora" (o servidor roda em UTC). Ver app/core/clock.py.
    timezone: str = "America/Sao_Paulo"

    # Banco central: cadastro de estúdios e usuários da plataforma.
    central_database_url: str = "sqlite:///./data/central.db"
    # Banco de cada estúdio. {slug} é substituído pelo identificador do estúdio (hífens viram _).
    # Postgres: postgresql+psycopg://user:pass@host:5432/pilates_{slug}
    tenant_database_url_template: str = "sqlite:///./data/tenants/{slug}.db"

    # Gere com: python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = "dev-only-insecure-key-troque-em-producao-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Lista JSON no .env, ex.: CORS_ORIGINS=["http://localhost:5173"]
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8081"]

    # Arquivos dos alunos (laudos). "local" = pasta no servidor; "s3" = S3/R2/B2/MinIO (uv sync --extra s3).
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./data/files"
    storage_max_upload_mb: int = 10
    storage_s3_bucket: str = ""
    storage_s3_endpoint_url: str | None = None  # vazio = AWS; R2/MinIO/B2 informam o endpoint
    storage_s3_region: str | None = None
    storage_s3_access_key: str | None = None
    storage_s3_secret_key: str | None = None

    # Superusuário da plataforma (cria/gerencia estúdios). Usado por: python -m app.cli init
    platform_admin_name: str = "Plataforma"
    platform_admin_email: str = "root@pilates.app"
    platform_admin_password: str = "root12345"


settings = Settings()
