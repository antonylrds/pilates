"""Papéis do Postgres: as requisições usam um papel sem privilégios de DDL.

Dois papéis:

- **admin** (``ADMIN_CENTRAL_DATABASE_URL`` / ``ADMIN_TENANT_DATABASE_URL_TEMPLATE``): cria bancos e roda migrações.
  É dono dos bancos e das tabelas.
- **requisições** (``CENTRAL_DATABASE_URL`` / ``TENANT_DATABASE_URL_TEMPLATE``): só lê e grava linhas
  (SELECT/INSERT/UPDATE/DELETE). Não cria nem apaga tabelas ou bancos, e não é superusuário. Um bug (ou injeção de SQL)
  nas rotas não consegue fazer ``DROP``/``ALTER`` nem ler outros bancos.

O papel das requisições é o usuário da URL ``CENTRAL_DATABASE_URL`` e é criado por ``ensure_runtime_role`` (com a senha
da própria URL). Depois de cada migração, ``grant_runtime_access`` concede o acesso ao banco migrado, e os privilégios
padrão cobrem as tabelas que migrações futuras criarem. Tudo é idempotente e só vale para Postgres com URLs de admin
configuradas e de outro usuário; fora disso (SQLite, dev) as funções não fazem nada.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def runtime_credentials() -> tuple[str, str | None] | None:
    """(papel, senha) usados nas requisições, se houver papel separado do admin; senão None."""
    if not settings.admin_central_database_url:
        return None
    runtime = make_url(settings.central_database_url)
    admin = make_url(settings.admin_central_database_url)
    if runtime.get_backend_name() != "postgresql" or not runtime.username or runtime.username == admin.username:
        return None
    return runtime.username, runtime.password


def ensure_runtime_role() -> bool:
    """Cria o papel das requisições (ou atualiza a senha dele). Devolve False se não há papel separado."""
    credentials = runtime_credentials()
    if credentials is None:
        return False
    role, password = credentials
    if not password:
        raise RuntimeError("A URL do papel das requisições (CENTRAL_DATABASE_URL) precisa ter senha")
    engine = create_engine(settings.admin_central_database_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
            verb = "ALTER" if exists else "CREATE"
            # O servidor monta o comando com %I/%L (identificador e literal escapados): sem interpolar a senha em Python.
            statement = conn.scalar(
                text("SELECT format(CAST(:t AS text), CAST(:r AS text), CAST(:p AS text))"),
                {
                    "t": f"{verb} ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION",
                    "r": role,
                    "p": password,
                },
            )
            with conn.connection.dbapi_connection.cursor() as cursor:  # sem processar '%' da senha
                cursor.execute(statement)
    finally:
        engine.dispose()
    return True


def grant_runtime_access(admin_url: str) -> None:
    """Concede ao papel das requisições o acesso mínimo ao banco ``admin_url`` (já migrado)."""
    credentials = runtime_credentials()
    if credentials is None or make_url(admin_url).get_backend_name() != "postgresql":
        return
    role = credentials[0]
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    quote = engine.dialect.identifier_preparer.quote
    database, role_q = quote(make_url(admin_url).database), quote(role)
    statements = [
        f"REVOKE ALL ON DATABASE {database} FROM PUBLIC",
        f"GRANT CONNECT ON DATABASE {database} TO {role_q}",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        f"GRANT USAGE ON SCHEMA public TO {role_q}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role_q}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role_q}",
        # Tabelas e sequências que migrações futuras criarem (pelo admin) já nascem com o acesso.
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role_q}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role_q}",
    ]
    try:
        with engine.connect() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()
