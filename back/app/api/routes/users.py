from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import Admin, get_or_404
from app.core.security import hash_password
from app.models.tenant import Teacher, User
from app.models.tenant.enums import UserRole
from app.schemas.auth import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _check_teacher_link(ctx, role: UserRole, teacher_id: int | None) -> None:
    if role == UserRole.TEACHER and teacher_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuário professor precisa estar vinculado a um professor")
    if teacher_id is not None:
        get_or_404(ctx.db, Teacher, teacher_id, "Professor")


@router.get("", response_model=list[UserRead])
def list_users(ctx: Admin):
    return ctx.db.scalars(select(User).order_by(User.name)).all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, ctx: Admin):
    _check_teacher_link(ctx, data.role, data.teacher_id)
    user = User(
        name=data.name,
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        role=data.role,
        teacher_id=data.teacher_id,
    )
    ctx.db.add(user)
    ctx.db.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, data: UserUpdate, ctx: Admin):
    user = get_or_404(ctx.db, User, user_id, "Usuário")
    changes = data.model_dump(exclude_unset=True)
    if user.id == ctx.user.id and (changes.get("is_active") is False or changes.get("role", UserRole.ADMIN) != UserRole.ADMIN):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode remover seu próprio acesso de admin")
    _check_teacher_link(ctx, changes.get("role", user.role), changes.get("teacher_id", user.teacher_id))
    if password := changes.pop("password", None):
        user.hashed_password = hash_password(password)
    if changes.get("email"):
        changes["email"] = changes["email"].lower()
    for field, value in changes.items():
        setattr(user, field, value)
    ctx.db.commit()
    return user
