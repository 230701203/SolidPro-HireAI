from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import AdminUser, DbSession
from app.models import AuditLog, User
from app.schemas.admin import AuditLogOut
from app.schemas.common import make_page

router = APIRouter(prefix="/audit-logs", tags=["Audit logs"])


@router.get("")
def list_audit_logs(
    _: AdminUser,
    db: DbSession,
    actor_id: int | None = None,
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=100, description="Prefix match, e.g. 'auth.' or 'employee.approved'"),
    search: str | None = Query(default=None, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    stmt = select(AuditLog, User.full_name, User.email).outerjoin(User, User.id == AuditLog.actor_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(AuditLog.action.ilike(like), User.email.ilike(like), User.full_name.ilike(like)))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    items = [
        AuditLogOut(
            id=a.id, created_at=a.created_at, actor_id=a.actor_id, actor_name=name, actor_email=email,
            action=a.action, entity_type=a.entity_type, entity_id=a.entity_id, details=a.details, ip_address=a.ip_address,
        )
        for a, name, email in rows
    ]
    return make_page(items, total, page, page_size)
