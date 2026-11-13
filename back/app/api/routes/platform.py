"""Administração da plataforma: cadastro de estúdios (cada um com banco próprio)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CentralDb, PlatformAdmin, apply_update, get_or_404
from app.core.ratelimit import LoginAttempt
from app.core.security import check_password, create_access_token
from app.db.studio_cache import studio_cache
from app.models.central import PlatformUser, Studio
from app.schemas.studio import PlatformLogin, PlatformToken, StudioCreate, StudioRead, StudioUpdate
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
