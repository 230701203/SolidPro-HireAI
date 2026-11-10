
from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import AdminUser, DbSession
from app.core.errors import AppError
from app.models import AccountStatus, Role, User
from app.schemas.admin import SetStatusRequest, UserListItem
from app.schemas.common import Message, make_page
from app.services import audit_service, auth_service, notification_service

router = APIRouter(prefix="/users", tags=["User management"])


@router.get("")
def list_users(
    _: AdminUser,
    db: DbSession,
    role: Role | None = None,
    status: AccountStatus | None = None,
    search: str | None = Query(default=None, max_length=100),
    sort: str = Query(default="created_at", pattern="^(created_at|last_login_at|full_name|email)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like), User.mobile.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = getattr(User, sort)
    order = col.asc().nulls_last() if direction == "asc" else col.desc().nulls_last()
    rows = db.scalars(stmt.order_by(order, User.id).limit(page_size).offset((page - 1) * page_size)).all()
    return make_page([UserListItem.model_validate(u, from_attributes=True) for u in rows], total, page, page_size)


def _target(db, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "User not found.")
    return user


@router.patch("/{user_id}/status", response_model=UserListItem)
def set_user_status(user_id: int, data: SetStatusRequest, request: Request, admin: AdminUser, db: DbSession):
    """Activate, suspend or deactivate an account. Approval of new employees goes through /employees."""
    user = _target(db, user_id)
    if user.id == admin.id:
        raise AppError(409, "invalid_state", "You cannot change the status of your own account.")
    if user.status in (AccountStatus.PENDING_EMAIL_VERIFICATION, AccountStatus.PENDING_APPROVAL, AccountStatus.REJECTED):
        raise AppError(
            409, "invalid_state", "This account has not completed registration. Employee registrations are handled in Employee Management."
        )
    target = AccountStatus(data.status)
    if user.status == target:
        raise AppError(409, "invalid_state", f"The account is already {target.value}.")

    previous = user.status
    user.status = target
    if target != AccountStatus.ACTIVE:
        user.token_version += 1  # invalidate existing sessions immediately
    notification_service.notify(
        db, user.id, "account_status", "Account status changed", f"Your account is now {target.value}."
    )
    audit_service.log_action(
        db, f"user.{target.value}", actor=admin, entity_type="user", entity_id=user.id,
        details={"from": previous.value, "to": target.value, "reason": data.reason}, request=request,
    )
    db.commit()
    return UserListItem.model_validate(user, from_attributes=True)


@router.post("/{user_id}/password-reset", response_model=Message)
def initiate_password_reset(user_id: int, background: BackgroundTasks, request: Request, admin: AdminUser, db: DbSession):
    """Email the user a password-reset link. The admin never sees or sets the password."""
    user = _target(db, user_id)
    if user.status in (AccountStatus.PENDING_EMAIL_VERIFICATION, AccountStatus.REJECTED):
        raise AppError(409, "invalid_state", "This account cannot reset its password in its current state.")
    auth_service.send_password_reset_email(db, user, background, initiated_by_admin=True)
    audit_service.log_action(db, "user.password_reset_initiated", actor=admin, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return Message(message=f"A password reset link was sent to {user.email}.")


@router.post("/{user_id}/unlock", response_model=Message)
def unlock_user(user_id: int, request: Request, admin: AdminUser, db: DbSession):
    user = _target(db, user_id)
    user.failed_login_attempts = 0
    user.locked_until = None
    audit_service.log_action(db, "user.unlocked", actor=admin, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return Message(message="Account unlocked.")
