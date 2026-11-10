from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_CODES
from app.models import EmployeePermission, Permission, Role, User
from app.schemas.auth import UserOut


def permission_codes_for(db: Session, user: User) -> list[str]:
    if user.role == Role.ADMIN:
        return sorted(PERMISSION_CODES)  # admins inherit every employee permission
    if user.role != Role.EMPLOYEE:
        return []
    rows = db.scalars(
        select(Permission.code)
        .join(EmployeePermission, EmployeePermission.permission_id == Permission.id)
        .where(EmployeePermission.user_id == user.id)
    ).all()
    return sorted(rows)


def permission_map(db: Session, user_ids: list[int]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = defaultdict(list)
    if not user_ids:
        return result
    rows = db.execute(
        select(EmployeePermission.user_id, Permission.code)
        .join(Permission, EmployeePermission.permission_id == Permission.id)
        .where(EmployeePermission.user_id.in_(user_ids))
    ).all()
    for uid, code in rows:
        result[uid].append(code)
    for codes in result.values():
        codes.sort()
    return result


def to_user_out(db: Session, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.permissions = permission_codes_for(db, user)
    if user.employee_profile:
        out.department = user.employee_profile.department
        out.designation = user.employee_profile.designation
    return out
