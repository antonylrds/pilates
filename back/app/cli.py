"""Comandos de manutenção.

  uv run python -m app.cli init      # migra o banco central e cria o usuário da plataforma
  uv run python -m app.cli migrate [--jobs 4]  # migra o central e os bancos de todos os estúdios (código 1 se algum falhar)
  uv run python -m app.cli create-studio --name "Studio X" --slug studio-x \\
        --admin-email admin@x.com --admin-password secret123
  uv run python -m app.cli seed-demo --slug demo --reset   # dados de demonstração
"""

import argparse
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.engines import central_session
from app.db.migrations import migrate_central, migrate_tenants
from app.models.central import PlatformUser, Studio
from app.schemas.studio import StudioCreate
from app.services.studios import create_studio


def init() -> None:
    migrate_central()
    with central_session() as db:
        email = settings.platform_admin_email.lower()
        if db.scalar(select(PlatformUser).where(PlatformUser.email == email)):
            print(f"Usuário da plataforma {email} já existe.")
            return
        db.add(
            PlatformUser(
                name=settings.platform_admin_name,
                email=email,
                hashed_password=hash_password(settings.platform_admin_password),
            )
        )
        db.commit()
        print(f"Usuário da plataforma criado: {email}")


def migrate(jobs: int = 1) -> int:
    """Migra o banco central e os de todos os estúdios. Um estúdio com erro não impede os outros: o comando
    termina com código 1 e lista os que falharam."""
    migrate_central()
    print("Banco central migrado.")
    with central_session() as db:
        slugs = list(db.scalars(select(Studio.slug).order_by(Studio.slug)).all())
    results = migrate_tenants(slugs, jobs)
    for slug, error in results.items():
        print(f"Estúdio {slug} migrado." if error is None else f"Estúdio {slug} FALHOU: {error}")
    failed = [slug for slug, error in results.items() if error is not None]
    if failed:
        print(f"{len(failed)} de {len(slugs)} estúdios falharam: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    mg = sub.add_parser("migrate", help="Migra o banco central e os dos estúdios")
    mg.add_argument("--jobs", type=int, default=1, help="Estúdios migrados em paralelo (processos)")
    cs = sub.add_parser("create-studio")
    cs.add_argument("--name", required=True)
    cs.add_argument("--slug", required=True)
    cs.add_argument("--admin-name", default="Administrador")
    cs.add_argument("--admin-email", required=True)
    cs.add_argument("--admin-password", required=True)
    sd = sub.add_parser("seed-demo", help="Popula um estúdio com dados de demonstração")
    sd.add_argument("--slug", required=True)
    sd.add_argument("--reset", action="store_true", help="Apaga os dados do estúdio (exceto usuários) antes")
    args = parser.parse_args()

    if args.command == "seed-demo":
        from app.demo_seed import seed

        seed(args.slug, reset=args.reset)
        return

    if args.command == "init":
        init()
    elif args.command == "migrate":
        raise SystemExit(migrate(args.jobs))
    elif args.command == "create-studio":
        studio = create_studio(
            StudioCreate(
                name=args.name,
                slug=args.slug,
                admin_name=args.admin_name,
                admin_email=args.admin_email,
                admin_password=args.admin_password,
            )
        )
        print(f"Estúdio criado: {studio.slug}")


if __name__ == "__main__":
    main()
