"""Object-level access rules for recruiters.

* Admin: everything.
* Employee: only openings they are assigned to (and therefore only the applicants of those
  openings), and only for the actions their permissions allow. Role alone never implies data access.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import EmployeeAssignment, EmployeePermission, Permission, Role, User


def has_permission(db: Session, user: User, code: str) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role != Role.EMPLOYEE:
        return False
    return (
        db.scalar(
            select(EmployeePermission.user_id)
            .join(Permission, Permission.id == EmployeePermission.permission_id)
            .where(EmployeePermission.user_id == user.id, Permission.code == code)
        )
        is not None
    )


def staff_scope(db: Session, user: User) -> list[int] | None:
    """None means unrestricted (admin). Otherwise the list of opening ids the employee is assigned to."""
    if user.role == Role.ADMIN:
        return None
    return list(db.scalars(select(EmployeeAssignment.opening_id).where(EmployeeAssignment.employee_id == user.id)).all())


def can_access_opening(db: Session, user: User, opening_id: int) -> bool:
    scope = staff_scope(db, user)
    return scope is None or opening_id in scope


def require_opening_access(db: Session, user: User, opening_id: int) -> None:
    # 404 rather than 403 so employees cannot probe for the existence of other openings.
    if not can_access_opening(db, user, opening_id):
        raise AppError(404, "not_found", "Opening not found.")


def require_perm(db: Session, user: User, code: str) -> None:
    if not has_permission(db, user, code):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
