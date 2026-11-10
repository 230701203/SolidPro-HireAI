from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import AdminUser, DbSession
from app.models import AccountStatus, EmployeeApproval, Permission, Role, User
from app.schemas.admin import (
    ApproveEmployeeRequest,
    ApprovalHistoryOut,
    EmployeeDetailOut,
    EmployeeOut,
    PermissionOut,
    RejectEmployeeRequest,
    SetPermissionsRequest,
)
from app.schemas.common import make_page
from app.services import employee_service
from app.services.user_service import permission_map

router = APIRouter(tags=["Employee management"])


def _employee_out(user: User, perms: dict[int, list[str]]) -> dict:
    p = user.employee_profile
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "mobile": user.mobile,
        "status": user.status,
        "created_at": user.created_at,
        "email_verified_at": user.email_verified_at,
        "last_login_at": user.last_login_at,
        "department": p.department if p else None,
        "designation": p.designation if p else None,
        "permissions": perms.get(user.id, []),
    }


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(_: AdminUser, db: DbSession):
    return db.scalars(select(Permission).order_by(Permission.category, Permission.code)).all()


@router.get("/employees")
def list_employees(
    _: AdminUser,
    db: DbSession,
    status: AccountStatus | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(User).where(User.role == Role.EMPLOYEE)
    if status:
        stmt = stmt.where(User.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = db.scalars(stmt.order_by(User.created_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    perms = permission_map(db, [u.id for u in users])
    return make_page([EmployeeOut(**_employee_out(u, perms)) for u in users], total, page, page_size)


@router.get("/employees/pending", response_model=list[EmployeeOut])
def pending_employees(_: AdminUser, db: DbSession):
    users = db.scalars(
        select(User)
        .where(User.role == Role.EMPLOYEE, User.status == AccountStatus.PENDING_APPROVAL)
        .order_by(User.created_at)
    ).all()
    return [EmployeeOut(**_employee_out(u, {})) for u in users]


@router.get("/employees/{employee_id}", response_model=EmployeeDetailOut)
def employee_detail(employee_id: int, _: AdminUser, db: DbSession):
    user = employee_service.get_employee(db, employee_id)
    rows = db.execute(
        select(EmployeeApproval, User.full_name)
        .outerjoin(User, User.id == EmployeeApproval.decided_by)
        .where(EmployeeApproval.employee_id == employee_id)
        .order_by(EmployeeApproval.decided_at.desc())
    ).all()
    approvals = [
        ApprovalHistoryOut(
            decision=a.decision,
            reason=a.reason,
            decided_by_name=name,
            decided_at=a.decided_at,
            permissions_granted=a.permissions_granted,
        )
        for a, name in rows
    ]
    return EmployeeDetailOut(**_employee_out(user, permission_map(db, [user.id])), approvals=approvals)


@router.post("/employees/{employee_id}/approve", response_model=EmployeeOut)
def approve_employee(
    employee_id: int, data: ApproveEmployeeRequest, background: BackgroundTasks, request: Request, admin: AdminUser, db: DbSession
):
    user = employee_service.approve(db, employee_service.get_employee(db, employee_id), data, admin, background, request)
    return EmployeeOut(**_employee_out(user, permission_map(db, [user.id])))


@router.post("/employees/{employee_id}/reject", response_model=EmployeeOut)
def reject_employee(
    employee_id: int, data: RejectEmployeeRequest, background: BackgroundTasks, request: Request, admin: AdminUser, db: DbSession
):
    user = employee_service.reject(db, employee_service.get_employee(db, employee_id), data.reason, admin, background, request)
    return EmployeeOut(**_employee_out(user, {}))


@router.put("/employees/{employee_id}/permissions", response_model=list[str])
def set_employee_permissions(employee_id: int, data: SetPermissionsRequest, request: Request, admin: AdminUser, db: DbSession):
    employee = employee_service.get_employee(db, employee_id)
    return employee_service.set_permissions(db, employee, data.permission_codes, admin, request)
