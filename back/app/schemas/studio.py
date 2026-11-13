from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import ORMModel

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$"


class StudioSettingsUpdate(BaseModel):
    """Campos que o admin do estúdio pode alterar."""

    name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    open_hour: int | None = Field(None, ge=0, le=23)
    close_hour: int | None = Field(None, ge=1, le=24)
    absence_consumes_credit: bool | None = None


class StudioCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=SLUG_PATTERN, description="Identificador único usado no login (ex.: studio-centro)")
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    open_hour: int = Field(6, ge=0, le=23)
    close_hour: int = Field(19, ge=1, le=24)
    absence_consumes_credit: bool = True
    # Primeiro usuário admin do estúdio
    admin_name: str = Field(min_length=2, max_length=120)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _hours(self):
        if self.close_hour <= self.open_hour:
            raise ValueError("close_hour deve ser maior que open_hour")
        return self


class StudioUpdate(StudioSettingsUpdate):
    is_active: bool | None = None


class StudioRead(ORMModel):
    id: int
    name: str
    slug: str
    email: str | None
    phone: str | None
    address: str | None
    open_hour: int
    close_hour: int
    absence_consumes_credit: bool
    is_active: bool
    created_at: datetime


class PlatformLogin(BaseModel):
    email: EmailStr
    password: str


class PlatformToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
