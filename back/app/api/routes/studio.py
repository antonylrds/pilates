"""Dados e configurações do próprio estúdio (editáveis pelo admin do estúdio)."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from app.api.deps import Admin, Staff
from app.db.engines import central_session
from app.models.central import Studio
from app.models.tenant import ClassGroup
from app.schemas.studio import StudioRead, StudioSettingsUpdate

router = APIRouter(prefix="/studio", tags=["studio"])


@router.get("", response_model=StudioRead)
def get_studio(ctx: Staff):
    return ctx.studio


@router.patch("", response_model=StudioRead)
def update_studio(data: StudioSettingsUpdate, ctx: Admin):
    changes = data.model_dump(exclude_unset=True)
    open_hour = changes.get("open_hour", ctx.studio.open_hour)
    close_hour = changes.get("close_hour", ctx.studio.close_hour)
    if close_hour <= open_hour:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "close_hour deve ser maior que open_hour")
    outside = ctx.db.scalar(
        select(ClassGroup.id).where(
            ClassGroup.end_date.is_(None),
            or_(ClassGroup.start_hour < open_hour, ClassGroup.start_hour > close_hour - 1),
        )
    )
    if outside:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Há turmas ativas fora do novo horário de funcionamento")

    with central_session() as central:
        studio = central.get(Studio, ctx.studio.id)
        for field, value in changes.items():
            setattr(studio, field, value)
        central.commit()
        central.refresh(studio)
        return studio
