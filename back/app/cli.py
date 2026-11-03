"""Comandos de manutenção.

  uv run python -m app.cli init      # migra o banco central e cria o usuário da plataforma
  uv run python -m app.cli migrate   # migra o banco central e os bancos de todos os estúdios
  uv run python -m app.cli create-studio --name "Studio X" --slug studio-x \\
        --admin-email admin@x.com --admin-password secret123
"""

import argparse

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.engines import central_session
from app.db.migrations import migrate_central, migrate_tenant
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


def migrate() -> None:
    migrate_central()
    print("Banco central migrado.")
    with central_session() as db:
        slugs = db.scalars(select(Studio.slug).order_by(Studio.slug)).all()
    for slug in slugs:
        migrate_tenant(slug)
        print(f"Estúdio {slug} migrado.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("migrate")
    cs = sub.add_parser("create-studio")
    cs.add_argument("--name", required=True)
    cs.add_argument("--slug", required=True)
    cs.add_argument("--admin-name", default="Administrador")
    cs.add_argument("--admin-email", required=True)
    cs.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    if args.command == "init":
        init()
    elif args.command == "migrate":
        migrate()
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
