from fastapi import BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AccountStatus,
    ApplicationStatus,
    ApplicationStatusHistory,
    CandidateProfile,
    CandidateResume,
    EmployeeAssignment,
    JobApplication,
    JobOpening,
    Role,
    User,
)
from app.models.base import utcnow
from app.schemas.recruitment import (
    ApplicationDetail,
    ApplyRequest,
    HistoryOut,
    ResumeOut,
)
from app.services import (
    access,
    audit_service,
    email_service,
    notification_service,
    profile_service,
)
from app.services.opening_service import is_open

S = ApplicationStatus
REVIEWABLE = (S.SUBMITTED, S.UNDER_REVIEW, S.INFO_REQUESTED)
TEAM = "Recruitment team"


def get_application(db: Session, application_id: int) -> JobApplication:
    a = db.get(JobApplication, application_id)
    if a is None:
        raise AppError(404, "not_found", "Application not found.")
    return a


def applicant_user(db: Session, app: JobApplication) -> User:
    cp = db.get(CandidateProfile, app.candidate_id)
    user = db.get(User, cp.user_id)
    assert user is not None
    return user


def require_owner(db: Session, user: User, app: JobApplication) -> None:
    cp = db.get(CandidateProfile, app.candidate_id)
    if cp is None or cp.user_id != user.id:
        raise AppError(404, "not_found", "Application not found.")  # never reveal other people's applications


def require_reviewer(db: Session, user: User, app: JobApplication) -> None:
    access.require_perm(db, user, "review_applications")
    access.require_opening_access(db, user, app.opening_id)


def _record(db: Session, app: JobApplication, to: ApplicationStatus, actor: User | None, comment: str | None, *, visible: bool, comment_only: bool = False) -> None:
    previous = app.status
    if not comment_only:
        app.status = to
    db.add(
        ApplicationStatusHistory(
            application_id=app.id, from_status=previous, to_status=previous if comment_only else to,
            changed_by=actor.id if actor else None, comment=comment, visible_to_applicant=visible,
        )
    )


def reviewers_for(db: Session, opening_id: int) -> list[User]:
    """Assigned active employees who may review applications; admins when nobody qualifies."""
    assigned = db.scalars(
        select(User).join(EmployeeAssignment, EmployeeAssignment.employee_id == User.id)
        .where(EmployeeAssignment.opening_id == opening_id, User.status == AccountStatus.ACTIVE)
    ).all()
    people = [u for u in assigned if access.has_permission(db, u, "review_applications")]
    return people or notification_service.active_admins(db)


def _notify_reviewers(db: Session, opening: JobOpening, type_: str, title: str, message: str, app_id: int) -> None:
    for u in reviewers_for(db, opening.id):
        notification_service.notify(db, u.id, type_, title, message, f"/applications/{app_id}")


# ------------------------------------------------------------------ applicant actions


def apply(db: Session, user: User, data: ApplyRequest, background: BackgroundTasks, request: Request) -> JobApplication:
    cp = profile_service.get_candidate(db, user)
    opening = db.get(JobOpening, data.opening_id)
    if opening is None or not is_open(opening):
        # Drafts must not be discoverable; closed/expired ones get a clear message.
        if opening is not None and opening.status.value == "published":
            raise AppError(409, "applications_closed", "The deadline for this opening has passed.")
        if opening is not None and opening.status.value == "closed":
            raise AppError(409, "applications_closed", "This opening is no longer accepting applications.")
        raise AppError(404, "not_found", "Opening not found.")
    if db.scalar(select(JobApplication.id).where(JobApplication.candidate_id == cp.id, JobApplication.opening_id == opening.id)):
        raise AppError(409, "already_applied", "You have already applied to this opening.")
    profile_service.require_ready_to_apply(db, cp, user)

    if data.resume_id is not None:
        resume = db.get(CandidateResume, data.resume_id)
        if resume is None or resume.candidate_id != cp.id:
            raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"resume_id": "Choose one of your own resumes"})
    else:
        resume = profile_service.current_resume(db, cp.id)
    assert resume is not None

    app = JobApplication(candidate_id=cp.id, opening_id=opening.id, resume_id=resume.id, cover_note=(data.cover_note or "").strip() or None, status=S.SUBMITTED)
    db.add(app)
    try:
        db.flush()
    except IntegrityError as exc:  # two simultaneous submissions
        db.rollback()
        raise AppError(409, "already_applied", "You have already applied to this opening.") from exc
    db.add(ApplicationStatusHistory(application_id=app.id, from_status=None, to_status=S.SUBMITTED, changed_by=user.id, comment="Application submitted", visible_to_applicant=True))

    _notify_reviewers(db, opening, "application_submitted", "New application", f"{user.full_name} applied for “{opening.title}”.", app.id)
    notification_service.notify(db, user.id, "application_submitted", "Application submitted", f"Your application for “{opening.title}” was received.", f"/my-applications/{app.id}")
    email_service.queue_email(
        db, background, to_email=user.email, subject=f"We received your application for {opening.title}", template="application_submitted",
        title="Application received", paragraphs=[f"Hello {user.full_name},", f"Thank you for applying for “{opening.title}”. Our recruitment team will review your application and contact you about next steps."],
        button=("View application", f"{get_settings().frontend_url.rstrip('/')}/my-applications/{app.id}"), user_id=user.id,
    )
    audit_service.log_action(db, "application.submitted", actor=user, entity_type="job_application", entity_id=app.id, details={"opening_id": opening.id, "resume_id": resume.id}, request=request)
    db.commit()
    return app


def withdraw(db: Session, app: JobApplication, user: User, request: Request) -> JobApplication:
    if app.status not in REVIEWABLE:
        raise AppError(409, "invalid_state", "This application can no longer be withdrawn.")
    _record(db, app, S.WITHDRAWN, user, "Withdrawn by applicant", visible=True)
    _notify_reviewers(db, app.opening, "application_withdrawn", "Application withdrawn", f"{user.full_name} withdrew their application for “{app.opening.title}”.", app.id)
    audit_service.log_action(db, "application.withdrawn", actor=user, entity_type="job_application", entity_id=app.id, request=request)
    db.commit()
    return app


def respond(db: Session, app: JobApplication, user: User, message: str, resume_id: int | None, request: Request) -> JobApplication:
    if app.status != S.INFO_REQUESTED:
        raise AppError(409, "invalid_state", "No additional information has been requested for this application.")
    if resume_id is not None:
        resume = db.get(CandidateResume, resume_id)
        if resume is None or resume.candidate_id != app.candidate_id:
            raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"resume_id": "Choose one of your own resumes"})
        app.resume_id = resume.id
    _record(db, app, S.UNDER_REVIEW, user, message, visible=True)
    _notify_reviewers(db, app.opening, "application_info_provided", "Applicant replied", f"{user.full_name} responded to your information request for “{app.opening.title}”.", app.id)
    audit_service.log_action(db, "application.info_provided", actor=user, entity_type="job_application", entity_id=app.id, details={"resume_id": app.resume_id}, request=request)
    db.commit()
    return app


# ------------------------------------------------------------------ reviewer actions


def _require_reviewable(app: JobApplication) -> None:
    if app.status not in REVIEWABLE:
        raise AppError(409, "invalid_state", f"This application is already {app.status.value.replace('_', ' ')} and can no longer be changed.")


def start_review(db: Session, app: JobApplication, reviewer: User, request: Request) -> JobApplication:
    if app.status != S.SUBMITTED:
        raise AppError(409, "invalid_state", "Only newly submitted applications can be moved to review.")
    _record(db, app, S.UNDER_REVIEW, reviewer, "Review started", visible=True)
    audit_service.log_action(db, "application.review_started", actor=reviewer, entity_type="job_application", entity_id=app.id, request=request)
    db.commit()
    return app


def _decide(db: Session, app: JobApplication, reviewer: User, to: ApplicationStatus, text: str | None, background: BackgroundTasks, request: Request, *, action: str, subject: str, headline: str, body: str) -> JobApplication:
    _require_reviewable(app)
    _record(db, app, to, reviewer, text, visible=True)
    if to in (S.APPROVED, S.REJECTED):
        app.decided_by, app.decided_at, app.decision_reason = reviewer.id, utcnow(), text
    candidate = applicant_user(db, app)
    title = app.opening.title
    notification_service.notify(db, candidate.id, f"application_{to.value}", headline, f"{body} (“{title}”)", f"/my-applications/{app.id}")
    paragraphs = [f"Hello {candidate.full_name},", f"{body} Position: “{title}”."]
    if text:
        paragraphs.append(f"Message from the recruitment team: {text}")
    email_service.queue_email(
        db, background, to_email=candidate.email, subject=subject.format(title=title), template=f"application_{to.value}", title=headline,
        paragraphs=paragraphs, button=("View application", f"{get_settings().frontend_url.rstrip('/')}/my-applications/{app.id}"), user_id=candidate.id,
    )
    audit_service.log_action(db, action, actor=reviewer, entity_type="job_application", entity_id=app.id, details={"note": text}, request=request)
    db.commit()
    return app


def approve(db, app, reviewer, note, background, request):
    return _decide(db, app, reviewer, S.APPROVED, note, background, request, action="application.approved",
                   subject="Update on your application for {title}", headline="Your application moved forward",
                   body="Good news: your application was approved for the next stage. You will receive assessment details separately.")


def reject(db, app, reviewer, reason, background, request):
    return _decide(db, app, reviewer, S.REJECTED, reason, background, request, action="application.rejected",
                   subject="Update on your application for {title}", headline="Update on your application",
                   body="Thank you for your interest. After review, we will not be moving forward with your application.")


def request_info(db, app, reviewer, message, background, request):
    if app.status not in (S.SUBMITTED, S.UNDER_REVIEW):
        raise AppError(409, "invalid_state", "Additional information can only be requested during review.")
    return _decide(db, app, reviewer, S.INFO_REQUESTED, message, background, request, action="application.info_requested",
                   subject="We need more information for {title}", headline="More information needed",
                   body="The recruitment team needs a little more information to continue reviewing your application. Sign in to reply.")


def add_comment(db: Session, app: JobApplication, reviewer: User, text: str, request: Request) -> JobApplication:
    _record(db, app, app.status, reviewer, text, visible=False, comment_only=True)
    audit_service.log_action(db, "application.commented", actor=reviewer, entity_type="job_application", entity_id=app.id, request=request)
    db.commit()
    return app


# ------------------------------------------------------------------ serialisation


def build_history(db: Session, app: JobApplication, *, for_applicant: bool) -> list[HistoryOut]:
    q = select(ApplicationStatusHistory, User.full_name, User.role).outerjoin(User, User.id == ApplicationStatusHistory.changed_by).where(ApplicationStatusHistory.application_id == app.id)
    if for_applicant:
        q = q.where(ApplicationStatusHistory.visible_to_applicant.is_(True))
    rows = db.execute(q.order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)).all()
    out = []
    for h, name, role in rows:
        is_staff = role in (Role.ADMIN, Role.EMPLOYEE)
        out.append(HistoryOut(
            id=h.id, from_status=h.from_status, to_status=h.to_status, comment=h.comment,
            actor_name=(TEAM if (for_applicant and is_staff) else name), actor_role=role.value if role else None,
            visible_to_applicant=h.visible_to_applicant, created_at=h.created_at,
        ))
    return out


def build_detail(db: Session, app: JobApplication, viewer: User) -> ApplicationDetail:
    staff = viewer.role in (Role.ADMIN, Role.EMPLOYEE)
    cp = db.get(CandidateProfile, app.candidate_id)
    cand_user = db.get(User, cp.user_id)
    decided_by = db.get(User, app.decided_by) if app.decided_by else None
    r = app.resume
    return ApplicationDetail(
        id=app.id, status=app.status, opening_id=app.opening_id, opening_title=app.opening.title, category_name=app.opening.category.name,
        candidate_id=cp.id, candidate_name=cand_user.full_name, candidate_email=cand_user.email,
        submitted_at=app.submitted_at, updated_at=app.updated_at, cover_note=app.cover_note,
        resume=ResumeOut(id=r.id, version=r.version, original_filename=r.original_filename, content_type=r.content_type, size_bytes=r.size_bytes, created_at=r.created_at, is_current=False),
        decision_reason=app.decision_reason, decided_at=app.decided_at,
        decided_by_name=(decided_by.full_name if (decided_by and staff) else (TEAM if decided_by else None)),
        history=build_history(db, app, for_applicant=not staff),
        can_review=staff and app.status in REVIEWABLE and access.has_permission(db, viewer, "review_applications") and access.can_access_opening(db, viewer, app.opening_id),
        candidate=profile_service.build_profile(db, cp) if staff else None,
    )


def list_applications(db: Session, *, opening_ids: list[int] | None = None, candidate_id: int | None = None, opening_id: int | None = None,
                      status: ApplicationStatus | None = None, search: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    """Shared listing. `opening_ids` restricts staff to their assigned openings (None = unrestricted)."""
    from sqlalchemy import func, or_

    q = (
        select(JobApplication, JobOpening.title, User.full_name, User.email)
        .join(JobOpening, JobOpening.id == JobApplication.opening_id)
        .join(CandidateProfile, CandidateProfile.id == JobApplication.candidate_id)
        .join(User, User.id == CandidateProfile.user_id)
    )
    if opening_ids is not None:
        q = q.where(JobApplication.opening_id.in_(opening_ids))
    if candidate_id is not None:
        q = q.where(JobApplication.candidate_id == candidate_id)
    if opening_id is not None:
        q = q.where(JobApplication.opening_id == opening_id)
    if status is not None:
        q = q.where(JobApplication.status == status)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(User.full_name.ilike(like), User.email.ilike(like), JobOpening.title.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(JobApplication.submitted_at.desc(), JobApplication.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    items = [
        {
            "id": a.id, "status": a.status, "opening_id": a.opening_id, "opening_title": title, "category_name": a.opening.category.name,
            "candidate_id": a.candidate_id, "candidate_name": name, "candidate_email": email, "submitted_at": a.submitted_at, "updated_at": a.updated_at,
        }
        for a, title, name, email in rows
    ]
    return items, total
