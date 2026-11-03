from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.security import hash_password
from app.db.engines import central_session, tenant_session
from app.db.migrations import provision_tenant
from app.models.central import Studio
from app.models.tenant import User
from app.models.tenant.enums import UserRole
from app.schemas.studio import StudioCreate


def create_studio(data: StudioCreate) -> Studio:
    """Registra o estúdio no banco central, cria o banco dele e o primeiro admin."""
    with central_session() as central:
        if central.scalar(select(Studio.id).where(Studio.slug == data.slug)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um estúdio com esse identificador")
        studio = Studio(**data.model_dump(exclude={"admin_name", "admin_email", "admin_password"}))
        central.add(studio)
        central.commit()

    try:
        provision_tenant(studio.slug)
        with tenant_session(studio.slug) as db:
            db.add(
                User(
                    name=data.admin_name,
                    email=data.admin_email.lower(),
                    hashed_password=hash_password(data.admin_password),
                    role=UserRole.ADMIN,
                )
            )
            db.commit()
    except Exception:
        with central_session() as central:
            central.delete(central.get(Studio, studio.id))
            central.commit()
        raise
    return studio
