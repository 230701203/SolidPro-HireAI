"""Role-aware dashboard data. Every number is computed from database rows.

Phase 1 only exposes what exists so far (accounts). Job, application and assessment metrics
are added by the phases that introduce those tables, rather than showing placeholder zeros.
"""

from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies.auth import CurrentUser, DbSession
from app.models import (
    AccountStatus,
    ApplicationStatus,
    CandidateProfile,
    JobApplication,
    JobOpening,
    Notification,
    OpeningStatus,
    Role,
    User,
)
from app.models.base import utcnow
from app.services import access, profile_service
from app.services.user_service import permission_codes_for

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


PENDING = (ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INFO_REQUESTED)


def _n(db, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


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
                "total_openings": _n(db, JobOpening),
                "active_openings": _n(db, JobOpening, JobOpening.status == OpeningStatus.PUBLISHED),
                "total_applications": _n(db, JobApplication),
                "pending_application_reviews": _n(db, JobApplication, JobApplication.status.in_(PENDING)),
            },
            "registrations_by_day": [{"date": d, **v} for d, v in by_day.items()],
            "recent_applicants": recent(User.role == Role.APPLICANT),
            "recent_employee_requests": recent(User.role == Role.EMPLOYEE, User.status == AccountStatus.PENDING_APPROVAL),
        }

    if user.role == Role.EMPLOYEE:
        scope = access.staff_scope(db, user) or []
        can_review = access.has_permission(db, user, "review_applications")
        apps = JobApplication.opening_id.in_(scope)
        return {
            **base,
            "permissions": permission_codes_for(db, user),
            "stats": {
                "assigned_openings": len(scope),
                "assigned_applicants": (db.scalar(select(func.count(func.distinct(JobApplication.candidate_id))).where(apps)) or 0) if can_review else 0,
                "pending_reviews": _n(db, JobApplication, apps, JobApplication.status.in_(PENDING)) if can_review else 0,
                "approved": _n(db, JobApplication, apps, JobApplication.status == ApplicationStatus.APPROVED) if can_review else 0,
                "shortlisted": _n(db, JobApplication, apps, JobApplication.status == ApplicationStatus.SHORTLISTED) if can_review else 0,
            },
        }

    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    mine = JobApplication.candidate_id == (cp.id if cp else -1)
    profile = profile_service.build_profile(db, cp) if cp else None
    return {
        **base,
        "member_since": user.created_at,
        "profile_completion": profile.completion if profile else 0,
        "profile_missing": profile.missing if profile else [],
        "stats": {
            "total_applications": _n(db, JobApplication, mine),
            "under_review": _n(db, JobApplication, mine, JobApplication.status.in_(PENDING)),
            "approved": _n(db, JobApplication, mine, JobApplication.status == ApplicationStatus.APPROVED),
            "shortlisted": _n(db, JobApplication, mine, JobApplication.status.in_((ApplicationStatus.SHORTLISTED, ApplicationStatus.SELECTED))),
            "rejected": _n(db, JobApplication, mine, JobApplication.status == ApplicationStatus.REJECTED),
        },
    }
