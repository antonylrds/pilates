from fastapi import APIRouter
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.api.deps import Staff, get_or_404
from app.models.tenant import Notification
from app.schemas.common import Message
from app.schemas.schedule import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead], summary="Avisos (ex.: alunos que precisam renovar o plano)")
def list_notifications(ctx: Staff, unread_only: bool = False, limit: int = 50):
    query = select(Notification).options(selectinload(Notification.student)).order_by(Notification.id.desc())
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    return ctx.db.scalars(query.limit(min(limit, 200))).all()


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, ctx: Staff):
    notification = get_or_404(ctx.db, Notification, notification_id, "Notificação")
    notification.is_read = True
    ctx.db.commit()
    return notification


@router.post("/read-all", response_model=Message)
def mark_all_read(ctx: Staff):
    ctx.db.execute(update(Notification).where(Notification.is_read.is_(False)).values(is_read=True))
    ctx.db.commit()
    return Message(detail="Notificações marcadas como lidas")
