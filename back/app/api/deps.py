from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.engines import central_session, tenant_session
from app.models.central import PlatformUser, Studio
from app.models.tenant import User
from app.models.tenant.enums import UserRole

tenant_oauth = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/token", scheme_name="Studio", description="client_id = slug do estúdio"
)
platform_oauth = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/platform/auth/token", scheme_name="Platform")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Credenciais inválidas ou expiradas", headers={"WWW-Authenticate": "Bearer"}
    )


def _decode(token: str, scope: str) -> dict[str, Any]:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise _unauthorized()
    if payload.get("scope") != scope:
        raise _unauthorized()
    return payload


# ---------- Plataforma (banco central) ----------
def get_central_db() -> Generator[Session, None, None]:
    db = central_session()
    try:
        yield db
    finally:
        db.close()


CentralDb = Annotated[Session, Depends(get_central_db)]


def get_platform_user(token: Annotated[str, Depends(platform_oauth)], db: CentralDb) -> PlatformUser:
    payload = _decode(token, "platform")
    user = db.get(PlatformUser, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


PlatformAdmin = Annotated[PlatformUser, Depends(get_platform_user)]


# ---------- Estúdio (banco do tenant) ----------
@dataclass
class TenantContext:
    studio: Studio
    db: Session
    user: User

    @property
    def is_admin(self) -> bool:
        return self.user.role == UserRole.ADMIN


def get_tenant(token: Annotated[str, Depends(tenant_oauth)]) -> Generator[TenantContext, None, None]:
    payload = _decode(token, "tenant")
    try:
        slug = str(payload["tenant"])
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized()

    with central_session() as central:
        studio = central.scalar(select(Studio).where(Studio.slug == slug))
    if studio is None or not studio.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Estúdio inativo ou inexistente")

    db = tenant_session(studio.slug)
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise _unauthorized()
        yield TenantContext(studio=studio, db=db, user=user)
    finally:
        db.close()


def require_roles(*roles: UserRole):
    def checker(ctx: Annotated[TenantContext, Depends(get_tenant)]) -> TenantContext:
        if ctx.user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão insuficiente")
        return ctx

    return checker


# Qualquer usuário do estúdio (admin ou professor).
Staff = Annotated[TenantContext, Depends(get_tenant)]
# Somente administradores do estúdio.
Admin = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN))]


M = TypeVar("M")


def get_or_404(db: Session, model: type[M], obj_id: int, label: str = "Registro") -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} não encontrado(a)")
    return obj


def apply_update(obj: Any, data) -> None:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
