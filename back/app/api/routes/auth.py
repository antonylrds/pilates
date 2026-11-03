from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import Staff
from app.core.security import create_access_token, hash_password, verify_password
from app.db.engines import central_session, tenant_session
from app.models.central import Studio
from app.models.tenant import User
from app.schemas.auth import LoginRequest, Me, PasswordChange, Token, UserRead
from app.schemas.common import Message
from app.schemas.studio import StudioRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _authenticate(slug: str, email: str, password: str) -> Token:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Estúdio, e-mail ou senha incorretos")
    with central_session() as central:
        studio = central.scalar(select(Studio).where(Studio.slug == slug.strip().lower()))
    if studio is None:
        raise invalid
    if not studio.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Estúdio inativo")
    with tenant_session(studio.slug) as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None or not verify_password(password, user.hashed_password):
            raise invalid
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário inativo")
        token = create_access_token(user.id, {"scope": "tenant", "tenant": studio.slug, "role": user.role.value})
        return Token(access_token=token, user=UserRead.model_validate(user), studio=StudioRead.model_validate(studio))


@router.post("/login", response_model=Token, summary="Login no estúdio (JSON) — front/mobile")
def login(data: LoginRequest):
    return _authenticate(data.studio, data.email, data.password)


@router.post("/token", response_model=Token, summary="Login OAuth2 (Swagger): client_id = slug do estúdio")
def login_form(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    if not form.client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe o slug do estúdio em client_id")
    return _authenticate(form.client_id, form.username, form.password)


@router.get("/me", response_model=Me)
def me(ctx: Staff):
    return Me(user=UserRead.model_validate(ctx.user), studio=StudioRead.model_validate(ctx.studio))


@router.post("/me/password", response_model=Message)
def change_password(data: PasswordChange, ctx: Staff):
    if not verify_password(data.current_password, ctx.user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta")
    ctx.user.hashed_password = hash_password(data.new_password)
    ctx.db.commit()
    return Message(detail="Senha alterada com sucesso")
