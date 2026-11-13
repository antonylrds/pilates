"""Administração da plataforma: cadastro de estúdios (cada um com banco próprio)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CentralDb, PlatformAdmin, apply_update, get_or_404
from app.core.ratelimit import LoginAttempt
from app.core.config import settings
from app.core.security import check_password, create_access_token
from app.db.engines import tenant_session
from app.db.studio_cache import studio_cache
from app.models.central import ImpersonationLog, PlatformUser, Studio
from app.models.tenant import User
from app.schemas.auth import Token, UserRead
from app.schemas.studio import (
    ImpersonateRequest,
    PlatformLogin,
    PlatformToken,
    StudioCreate,
    StudioRead,
    StudioUpdate,
)
from app.services.studios import create_studio

router = APIRouter(prefix="/platform", tags=["platform"])


def _login(request: Request, db: CentralDb, email: str, password: str) -> PlatformToken:
    attempt = LoginAttempt(request, "platform", email)
    attempt.check()
    user = db.scalar(select(PlatformUser).where(PlatformUser.email == email.lower()))
    if not check_password(password, user.hashed_password if user else None) or not user.is_active:
        attempt.failed()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos")
    attempt.succeeded()
    return PlatformToken(access_token=create_access_token(user.id, {"scope": "platform"}))


@router.post("/auth/login", response_model=PlatformToken)
def login(data: PlatformLogin, request: Request, db: CentralDb):
    return _login(request, db, data.email, data.password)


@router.post("/auth/token", response_model=PlatformToken, include_in_schema=False)
def login_form(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: CentralDb):
    return _login(request, db, form.username, form.password)


@router.get("/studios", response_model=list[StudioRead])
def list_studios(db: CentralDb, _: PlatformAdmin):
    return db.scalars(select(Studio).order_by(Studio.name)).all()


@router.post(
    "/studios",
    response_model=StudioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria o estúdio, provisiona o banco dele e o primeiro admin",
)
def new_studio(data: StudioCreate, _: PlatformAdmin):
    return create_studio(data)


@router.get("/studios/{studio_id}", response_model=StudioRead)
def get_studio(studio_id: int, db: CentralDb, _: PlatformAdmin):
    return get_or_404(db, Studio, studio_id, "Estúdio")


@router.patch("/studios/{studio_id}", response_model=StudioRead, summary="Atualiza ou ativa/desativa um estúdio")
def update_studio(studio_id: int, data: StudioUpdate, db: CentralDb, _: PlatformAdmin):
    studio = get_or_404(db, Studio, studio_id, "Estúdio")
    apply_update(studio, data)
    if studio.close_hour <= studio.open_hour:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "close_hour deve ser maior que open_hour")
    db.commit()
    db.refresh(studio)
    studio_cache.invalidate(studio.slug)
    return studio


@router.get(
    "/studios/{studio_id}/users",
    response_model=list[UserRead],
    summary="Usuários do estúdio (para escolher como ver o sistema)",
)
def studio_users(studio_id: int, db: CentralDb, _: PlatformAdmin):
    studio = get_or_404(db, Studio, studio_id, "Estúdio")
    with tenant_session(studio.slug) as tenant_db:
        users = tenant_db.scalars(select(User).order_by(User.role, User.name)).all()
        return [UserRead.model_validate(u) for u in users]


@router.post(
    "/studios/{studio_id}/impersonate",
    response_model=Token,
    summary='"Ver como": token de estúdio para ver (e agir) como um admin ou professor',
    description="Devolve o mesmo formato do login do estúdio, com `impersonated_by`. O token dura "
    "`IMPERSONATION_EXPIRE_MINUTES`, deixa de valer se o usuário da plataforma for desativado, e os registros "
    "(histórico, laudos) levam o nome do operador. Trocar ou redefinir senhas fica bloqueado. Cada uso é "
    "gravado no log central (`impersonation_logs`).",
)
def impersonate(studio_id: int, data: ImpersonateRequest, db: CentralDb, operator: PlatformAdmin):
    studio = get_or_404(db, Studio, studio_id, "Estúdio")
    if not studio.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Estúdio inativo")
    with tenant_session(studio.slug) as tenant_db:
        user = tenant_db.get(User, data.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado ou inativo neste estúdio")
        token = create_access_token(
            user.id,
            {"scope": "tenant", "tenant": studio.slug, "role": user.role.value, "imp": operator.id},
            expires_minutes=settings.impersonation_expire_minutes,
        )
        user_read = UserRead.model_validate(user)
    db.add(
        ImpersonationLog(
            platform_user_id=operator.id,
            platform_user_name=operator.name,
            studio_id=studio.id,
            studio_slug=studio.slug,
            as_user_id=user_read.id,
            as_user_name=user_read.name,
            as_role=user_read.role.value,
        )
    )
    db.commit()
    return Token(
        access_token=token, user=user_read, studio=StudioRead.model_validate(studio), impersonated_by=operator.name
    )
