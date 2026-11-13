from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(
    subject: str | int, extra: dict[str, Any] | None = None, expires_minutes: int | None = None
) -> str:
    minutes = settings.access_token_expire_minutes if expires_minutes is None else expires_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire, **(extra or {})}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


_dummy_hash: str | None = None


def check_password(password: str, hashed: str | None) -> bool:
    """Como ``verify_password``, mas gasta o mesmo tempo quando o usuário não existe (``hashed`` None).

    Sem isso, e-mail inexistente responde bem mais rápido que senha errada (o hash é caro) e revela quem tem conta.
    """
    global _dummy_hash
    if hashed is None:
        if _dummy_hash is None:
            _dummy_hash = password_hash.hash("senha-ficticia-para-igualar-o-tempo")
        password_hash.verify(password, _dummy_hash)
        return False
    return password_hash.verify(password, hashed)
