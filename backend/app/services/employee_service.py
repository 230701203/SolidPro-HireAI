from fastapi import BackgroundTasks, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AccountStatus,
    ApprovalDecision,
    EmployeeApproval,
    EmployeePermission,
    EmployeeProfile,
    Permission,
    Role,
    User,
)
from app.models.base import utcnow
from app.schemas.admin import ApproveEmployeeRequest
from app.services import audit_service, email_service, notification_service
from app.services.user_service import permission_codes_for


def get_employee(db: Session, employee_id: int) -> User:
    user = db.get(User, employee_id)
    if user is None or user.role != Role.EMPLOYEE:
        raise AppError(404, "not_found", "Employee not found.")
    return user


def _replace_permissions(db: Session, employee: User, codes: list[str], granted_by: User) -> None:
    db.execute(delete(EmployeePermission).where(EmployeePermission.user_id == employee.id))
    if codes:
        perms = db.scalars(select(Permission).where(Permission.code.in_(codes))).all()
        if len(perms) != len(set(codes)):
            raise AppError(
                500, "permissions_not_seeded", "Permission catalogue is out of date. Run `python -m app.cli bootstrap`."
            )
        for p in perms:
            db.add(EmployeePermission(user_id=employee.id, permission_id=p.id, granted_by=granted_by.id))
    db.flush()


def approve(db: Session, employee: User, data: ApproveEmployeeRequest, admin: User, background: BackgroundTasks, request: Request) -> User:
    if employee.status not in (AccountStatus.PENDING_APPROVAL, AccountStatus.REJECTED):
        raise AppError(409, "invalid_state", "Only registrations that are pending or rejected can be approved.")

    _replace_permissions(db, employee, data.permission_codes, admin)
    if employee.employee_profile is None:
        employee.employee_profile = EmployeeProfile()
    if data.department is not None:
        employee.employee_profile.department = data.department
    if data.designation is not None:
        employee.employee_profile.designation = data.designation

    employee.status = AccountStatus.ACTIVE
    db.add(
        EmployeeApproval(
            employee_id=employee.id,
            decided_by=admin.id,
            decision=ApprovalDecision.APPROVED,
            permissions_granted=data.permission_codes,
            decided_at=utcnow(),
        )
    )
    s = get_settings()
    notification_service.notify(
        db, employee.id, "employee_approved", "Registration approved", "Your account is active. You can now sign in.", "/dashboard"
    )
    email_service.queue_email(
        db,
        background,
        to_email=employee.email,
        subject=f"Your {s.app_name} account has been approved",
        template="employee_approved",
        title="Your registration was approved",
        paragraphs=[f"Hello {employee.full_name},", "An administrator approved your account. You can sign in now."],
        button=("Sign in", f"{s.frontend_url.rstrip('/')}/login"),
        user_id=employee.id,
    )
    audit_service.log_action(
        db, "employee.approved", actor=admin, entity_type="user", entity_id=employee.id,
        details={"permissions": data.permission_codes}, request=request,
    )
    db.commit()
    return employee


def reject(db: Session, employee: User, reason: str, admin: User, background: BackgroundTasks, request: Request) -> User:
    if employee.status != AccountStatus.PENDING_APPROVAL:
        raise AppError(409, "invalid_state", "Only pending registrations can be rejected. Use Suspend for active accounts.")

    employee.status = AccountStatus.REJECTED
    db.add(
        EmployeeApproval(
            employee_id=employee.id, decided_by=admin.id, decision=ApprovalDecision.REJECTED, reason=reason, decided_at=utcnow()
        )
    )
    s = get_settings()
    email_service.queue_email(
        db,
        background,
        to_email=employee.email,
        subject=f"Update on your {s.app_name} registration",
        template="employee_rejected",
        title="Your registration was not approved",
        paragraphs=[
            f"Hello {employee.full_name},",
            "An administrator reviewed your registration and could not approve it.",
            f"Reason: {reason}",
            f"If you think this is a mistake, contact {s.support_email}.",
        ],
        user_id=employee.id,
    )
    audit_service.log_action(
        db, "employee.rejected", actor=admin, entity_type="user", entity_id=employee.id, details={"reason": reason}, request=request
    )
    db.commit()
    return employee


def set_permissions(db: Session, employee: User, codes: list[str], admin: User, request: Request) -> list[str]:
    if employee.status != AccountStatus.ACTIVE:
        raise AppError(409, "invalid_state", "Permissions can only be edited for active employees. Approve the registration first.")
    before = permission_codes_for(db, employee)
    _replace_permissions(db, employee, codes, admin)
    after = sorted(set(codes))
    notification_service.notify(
        db, employee.id, "permissions_changed", "Your access was updated", "An administrator changed your recruitment permissions."
    )
    audit_service.log_action(
        db, "employee.permissions_changed", actor=admin, entity_type="user", entity_id=employee.id,
        details={"before": before, "after": after}, request=request,
    )
    db.commit()
    return after
