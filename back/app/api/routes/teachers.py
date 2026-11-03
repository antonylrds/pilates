from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import Admin, Staff, apply_update, get_or_404
from app.models.tenant import ClassGroup, Teacher
from app.schemas.people import TeacherCreate, TeacherRead, TeacherUpdate

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("", response_model=list[TeacherRead])
def list_teachers(ctx: Staff, is_active: bool | None = True):
    query = select(Teacher).order_by(Teacher.name)
    if is_active is not None:
        query = query.where(Teacher.is_active == is_active)
    return ctx.db.scalars(query).all()


@router.post("", response_model=TeacherRead, status_code=status.HTTP_201_CREATED)
def create_teacher(data: TeacherCreate, ctx: Admin):
    teacher = Teacher(**data.model_dump())
    ctx.db.add(teacher)
    ctx.db.commit()
    return teacher


@router.get("/{teacher_id}", response_model=TeacherRead)
def get_teacher(teacher_id: int, ctx: Staff):
    return get_or_404(ctx.db, Teacher, teacher_id, "Professor")


@router.patch("/{teacher_id}", response_model=TeacherRead)
def update_teacher(teacher_id: int, data: TeacherUpdate, ctx: Admin):
    teacher = get_or_404(ctx.db, Teacher, teacher_id, "Professor")
    if data.is_active is False:
        _ensure_without_groups(ctx, teacher.id)
    apply_update(teacher, data)
    ctx.db.commit()
    return teacher


def _ensure_without_groups(ctx, teacher_id: int) -> None:
    if ctx.db.scalar(select(ClassGroup.id).where(ClassGroup.teacher_id == teacher_id, ClassGroup.end_date.is_(None))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Professor possui turmas ativas; transfira-as antes")


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Inativa o professor")
def deactivate_teacher(teacher_id: int, ctx: Admin):
    teacher = get_or_404(ctx.db, Teacher, teacher_id, "Professor")
    _ensure_without_groups(ctx, teacher.id)
    teacher.is_active = False
    ctx.db.commit()
