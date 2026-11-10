"""Role-aware dashboard data. Every number is computed from database rows.

Phase 1 only exposes what exists so far (accounts). Job, application and assessment metrics
are added by the phases that introduce those tables, rather than showing placeholder zeros.
"""

from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies.auth import CurrentUser, DbSession
from app.models import AccountStatus, Notification, Role, User
from app.models.base import utcnow
from app.services.user_service import permission_codes_for

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _count(db, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0


@router.get("/summary")
def summary(user: CurrentUser, db: DbSession):
    unread = (
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
        )
        or 0
    )
    base = {"role": user.role.value, "unread_notifications": unread}

    if user.role == Role.ADMIN:
        since = utcnow() - timedelta(days=29)
        day = func.date_trunc("day", User.created_at)
        rows = db.execute(
            select(day.label("d"), User.role, func.count())
            .where(User.created_at >= since, User.role.in_([Role.APPLICANT, Role.EMPLOYEE]))
            .group_by("d", User.role)
        ).all()
        by_day: dict[str, dict[str, int]] = {}
        for i in range(30):
            d = (since + timedelta(days=i)).date().isoformat()
            by_day[d] = {"applicants": 0, "employees": 0}
        for d, role, n in rows:
            key = d.date().isoformat()
            if key in by_day:
                by_day[key]["applicants" if role == Role.APPLICANT else "employees"] = n

        def recent(*conds):
            return [
                {"id": u.id, "full_name": u.full_name, "email": u.email, "created_at": u.created_at}
                for u in db.scalars(select(User).where(*conds).order_by(User.created_at.desc()).limit(5)).all()
            ]

        return {
            **base,
            "cards": {
                "total_applicants": _count(db, User.role == Role.APPLICANT),
                "total_employees": _count(db, User.role == Role.EMPLOYEE, User.status == AccountStatus.ACTIVE),
                "pending_employee_approvals": _count(db, User.role == Role.EMPLOYEE, User.status == AccountStatus.PENDING_APPROVAL),
                "suspended_accounts": _count(db, User.status.in_([AccountStatus.SUSPENDED, AccountStatus.DEACTIVATED])),
            },
            "registrations_by_day": [{"date": d, **v} for d, v in by_day.items()],
            "recent_applicants": recent(User.role == Role.APPLICANT),
            "recent_employee_requests": recent(User.role == Role.EMPLOYEE, User.status == AccountStatus.PENDING_APPROVAL),
        }

    if user.role == Role.EMPLOYEE:
        return {**base, "permissions": permission_codes_for(db, user)}

    return {**base, "member_since": user.created_at}
