"""Authentication and authorization dependencies. Every check runs server-side on every request."""

from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_access_token, decode_access_token
from app.database import get_db
from app.models import AccountStatus, EmployeePermission, Permission, Role, User

DbSession = Annotated[Session, Depends(get_db)]


def set_session_cookie(response: Response, user: User, *, remember_me: bool) -> None:
    s = get_settings()
    token, lifetime = create_access_token(user.id, user.token_version, remember_me=remember_me)
    response.set_cookie(
        key=s.cookie_name,
        value=token,
        max_age=lifetime if remember_me else None,  # session cookie unless "remember me"
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.cookie_name, path="/", httponly=True, secure=s.cookie_secure, samesite=s.cookie_samesite)


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().cookie_name)


_STATUS_ERRORS = {
    AccountStatus.PENDING_EMAIL_VERIFICATION: ("email_not_verified", "Please verify your email address."),
    AccountStatus.PENDING_APPROVAL: ("pending_approval", "Your account is waiting for administrator approval."),
    AccountStatus.REJECTED: ("account_rejected", "Your registration was not approved."),
    AccountStatus.SUSPENDED: ("account_suspended", "Your account has been suspended."),
    AccountStatus.DEACTIVATED: ("account_deactivated", "Your account has been deactivated."),
}


def get_session_user(request: Request, db: DbSession) -> User:
    """Authenticated, active user. Does NOT enforce the forced password change (used by change-password)."""
    token = _token_from_request(request)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise AppError(401, "not_authenticated", "Please sign in to continue.")
    user = db.get(User, int(payload["sub"]))
    if user is None or payload.get("ver") != user.token_version:
        raise AppError(401, "session_expired", "Your session has expired. Please sign in again.")
    if user.status != AccountStatus.ACTIVE:
        code, message = _STATUS_ERRORS[user.status]
        raise AppError(403, code, message)
    return user


def get_current_user(user: Annotated[User, Depends(get_session_user)]) -> User:
    if user.must_change_password:
        raise AppError(403, "password_change_required", "You must change your password before continuing.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionUser = Annotated[User, Depends(get_session_user)]


def require_roles(*roles: Role):
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "You do not have access to this resource.")
        return user

    return dependency


def require_permission(code: str):
    """Admins pass automatically; employees need the permission granted by an admin."""

    def dependency(user: CurrentUser, db: DbSession) -> User:
        if user.role == Role.ADMIN:
            return user
        if user.role == Role.EMPLOYEE:
            has = db.scalar(
                select(EmployeePermission.user_id)
                .join(Permission, Permission.id == EmployeePermission.permission_id)
                .where(EmployeePermission.user_id == user.id, Permission.code == code)
            )
            if has is not None:
                return user
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")

    return dependency


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
StaffUser = Annotated[User, Depends(require_roles(Role.ADMIN, Role.EMPLOYEE))]
