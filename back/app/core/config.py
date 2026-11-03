from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    app_name: str = "Pilates Studio API"
    api_prefix: str = "/api/v1"

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

    # Superusuário da plataforma (cria/gerencia estúdios). Usado por: python -m app.cli init
    platform_admin_name: str = "Plataforma"
    platform_admin_email: str = "root@pilates.app"
    platform_admin_password: str = "root12345"


settings = Settings()
