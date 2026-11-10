from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.errors import AppError
from app.models import Notification
from app.models.base import utcnow
from app.schemas.admin import NotificationOut
from app.schemas.common import Message, make_page

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return make_page([NotificationOut.model_validate(n) for n in rows], total, page, page_size)


@router.get("/unread-count")
def unread_count(user: CurrentUser, db: DbSession):
    n = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    )
    return {"count": n or 0}


@router.post("/read-all", response_model=Message)
def mark_all_read(user: CurrentUser, db: DbSession):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=utcnow())
    )
    db.commit()
    return Message(message="All notifications marked as read.")


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: CurrentUser, db: DbSession):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:  # other users' notifications look nonexistent
        raise AppError(404, "not_found", "Notification not found.")
    if not n.is_read:
        n.is_read = True
        n.read_at = utcnow()
        db.commit()
    return NotificationOut.model_validate(n)
