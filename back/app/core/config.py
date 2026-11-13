from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores de desenvolvimento: aceitos só com ENVIRONMENT=dev (veja Settings._no_dev_secrets_in_production).
DEV_SECRET_KEY = "dev-only-insecure-key-troque-em-producao-0123456789"
DEV_PLATFORM_ADMIN_PASSWORD = "root12345"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    app_name: str = "Pilates Studio API"
    # "production" recusa subir com os segredos de desenvolvimento (SECRET_KEY e senha do admin da plataforma).
    environment: Literal["dev", "production"] = "dev"
    api_prefix: str = "/api/v1"
    # Fuso dos estúdios: define "hoje" e "agora" (o servidor roda em UTC). Ver app/core/clock.py.
    timezone: str = "America/Sao_Paulo"

    # Banco central: cadastro de estúdios e usuários da plataforma.
    central_database_url: str = "sqlite:///./data/central.db"
    # Banco de cada estúdio. {slug} é substituído pelo identificador do estúdio (hífens viram _).
    # Postgres: postgresql+psycopg://user:pass@host:5432/pilates_{slug}
    tenant_database_url_template: str = "sqlite:///./data/tenants/{slug}.db"

    # Papel de admin do Postgres (cria bancos e roda migrações). Se definidos, de outro usuário que as URLs acima, as
    # requisições usam um papel sem privilégios de DDL (veja app/db/roles.py). Vazio = mesmo usuário (SQLite, dev).
    admin_central_database_url: str | None = None
    admin_tenant_database_url_template: str | None = None

    # Conexões: cada estúdio tem o próprio pool. Mantém poucas conexões ociosas por estúdio (pool_size) e descarta
    # os engines de estúdios sem uso (idle) ou além do limite (max_cached, os menos usados primeiro). No Postgres,
    # conexões ociosas ≈ estúdios em cache × pool_size: mantenha abaixo de max_connections (padrão 100).
    tenant_pool_size: int = 1
    tenant_pool_max_overflow: int = 2
    tenant_engine_idle_seconds: int = 600
    tenant_engine_max_cached: int = 50
    # Cache (por processo) do cadastro de estúdios usado em toda requisição autenticada. 0 desliga.
    studio_cache_seconds: int = 30

    # Gere com: python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = DEV_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Limite de tentativas de login que falharam (em memória, por processo): por IP+conta e por IP, na janela.
    login_max_attempts: int = 5
    login_max_attempts_per_ip: int = 30
    login_window_seconds: int = 15 * 60

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
    platform_admin_password: str = DEV_PLATFORM_ADMIN_PASSWORD

    @model_validator(mode="after")
    def _no_dev_secrets_in_production(self):
        if self.environment != "production":
            return self
        problems = []
        if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
            problems.append("SECRET_KEY deve ser definida com pelo menos 32 caracteres (não use a de desenvolvimento)")
        if self.platform_admin_password == DEV_PLATFORM_ADMIN_PASSWORD:
            problems.append("PLATFORM_ADMIN_PASSWORD não pode ser a senha padrão de desenvolvimento")
        if problems:
            raise ValueError("Configuração insegura para produção: " + "; ".join(problems))
        return self


settings = Settings()
