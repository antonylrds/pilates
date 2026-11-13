from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.tenant.enums import UserRole
from app.schemas.common import ORMModel
from app.schemas.studio import StudioRead


class LoginRequest(BaseModel):
    studio: str = Field(description="Slug do estúdio")
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.TEACHER
    teacher_id: int | None = Field(None, description="Obrigatório para usuários com papel teacher")


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=128)
    role: UserRole | None = None
    teacher_id: int | None = None
    is_active: bool | None = None


class UserRead(ORMModel):
    id: int
    name: str
    email: str
    role: UserRole
    teacher_id: int | None
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    studio: StudioRead


class Me(BaseModel):
    user: UserRead
    studio: StudioRead


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
