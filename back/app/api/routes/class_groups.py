from datetime import date

from fastapi import APIRouter, status
from sqlalchemy import or_, select

from app.api.deps import Admin, Staff
from app.models.tenant import ClassGroup
from app.schemas.people import StudentSummary
from app.schemas.schedule import ClassGroupCreate, ClassGroupDetail, ClassGroupRead, ClassGroupUpdate
from app.services import schedule as service

router = APIRouter(prefix="/class-groups", tags=["class groups (turmas)"])


def _detail(group: ClassGroup) -> ClassGroupDetail:
    today = date.today()
    students = sorted(
        (e.student for e in group.enrollments if e.end_date is None or e.end_date >= today),
        key=lambda s: s.name.lower(),
    )
    return ClassGroupDetail(
        **ClassGroupRead.model_validate(group).model_dump(),
        students=[StudentSummary.model_validate(s) for s in students],
    )


@router.get("", response_model=list[ClassGroupRead])
def list_groups(
    ctx: Staff,
    weekday: int | None = None,
    room_id: int | None = None,
    teacher_id: int | None = None,
    include_ended: bool = False,
):
    query = select(ClassGroup).options(*service.GROUP_LOAD).order_by(ClassGroup.weekday, ClassGroup.start_hour)
    if not include_ended:
        query = query.where(or_(ClassGroup.end_date.is_(None), ClassGroup.end_date >= date.today()))
    if weekday is not None:
        query = query.where(ClassGroup.weekday == weekday)
    if room_id:
        query = query.where(ClassGroup.room_id == room_id)
    if teacher_id:
        query = query.where(ClassGroup.teacher_id == teacher_id)
    return ctx.db.scalars(query).all()


@router.post(
    "",
    response_model=ClassGroupDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Cria turma (seg-sex, 1h, sem conflito de sala/professor)",
)
def create_group(data: ClassGroupCreate, ctx: Admin):
    group = service.create_group(ctx.db, ctx.studio, data)
    return _detail(service.load_group(ctx.db, group.id))


@router.get("/{group_id}", response_model=ClassGroupDetail)
def get_group(group_id: int, ctx: Staff):
    return _detail(service.load_group(ctx.db, group_id))


@router.patch(
    "/{group_id}",
    response_model=ClassGroupDetail,
    summary="Altera sala, professor, nome ou capacidade (dia/hora: crie outra turma)",
)
def update_group(group_id: int, data: ClassGroupUpdate, ctx: Admin):
    group = service.load_group(ctx.db, group_id)
    service.update_group(ctx.db, group, data)
    ctx.db.expire_all()
    return _detail(service.load_group(ctx.db, group_id))


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerra a turma a partir de uma data e libera os alunos",
)
def end_group(group_id: int, ctx: Admin, end_date: date | None = None):
    group = service.load_group(ctx.db, group_id)
    service.end_group(ctx.db, group, end_date or date.today())
