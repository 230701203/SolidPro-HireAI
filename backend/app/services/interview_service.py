"""Interview management (Phase 6). Allowed once an application is shortlisted.

Feedback is internal: applicants never see it. The assigned interviewer may view their own interview and record feedback
even without `manage_interviews`, but still only within openings they are assigned to.
"""

from datetime import datetime

from fastapi import BackgroundTasks, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AccountStatus,
    ApplicationStatus,
    CandidateProfile,
    Interview,
    InterviewFeedback,
    InterviewStatus,
    JobApplication,
    JobOpening,
    Role,
    User,
)
from app.models.base import utcnow
from app.schemas.interview import (
    FeedbackIn, FeedbackOut, InterviewCreate, InterviewerRef, InterviewOut, InterviewUpdate, MyInterview,
)
from app.services import access, application_service, audit_service, email_service, notification_service

UPCOMING = (InterviewStatus.SCHEDULED, InterviewStatus.RESCHEDULED)


def _fmt(dt: datetime) -> str:
    return dt.astimezone().strftime("%d %b %Y, %H:%M %Z")


def _staff(user: User) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")


def get_interview(db: Session, interview_id: int) -> Interview:
    iv = db.get(Interview, interview_id)
    if iv is None:
        raise AppError(404, "not_found", "Interview not found.")
    return iv


def _can_manage(db: Session, user: User, iv: Interview) -> bool:
    app = db.get(JobApplication, iv.application_id)
    return bool(app) and access.can_access_opening(db, user, app.opening_id) and access.has_permission(db, user, "manage_interviews")  # type: ignore[union-attr]


def _can_feedback(db: Session, user: User, iv: Interview) -> bool:
    app = db.get(JobApplication, iv.application_id)
    if not app or not access.can_access_opening(db, user, app.opening_id):
        return False
    return _can_manage(db, user, iv) or iv.interviewer_id == user.id


def require_view(db: Session, user: User, iv: Interview) -> None:
    _staff(user)
    if not _can_feedback(db, user, iv):
        raise AppError(404, "not_found", "Interview not found.")  # do not reveal other people's interviews


def _interviewer(db: Session, app: JobApplication, interviewer_id: int | None) -> User | None:
    if interviewer_id is None:
        return None
    u = db.get(User, interviewer_id)
    if u is None or u.role not in (Role.ADMIN, Role.EMPLOYEE) or u.status != AccountStatus.ACTIVE or not access.can_access_opening(db, u, app.opening_id):
        raise AppError(422, "bad_interviewer", "Choose an active employee or admin who has access to this opening.", fields={"interviewer_id": "Not a valid interviewer for this opening"})
    return u


def out(db: Session, user: User, iv: Interview) -> InterviewOut:
    app = db.get(JobApplication, iv.application_id)
    cand = application_service.applicant_user(db, app)  # type: ignore[arg-type]
    fb = db.scalar(select(InterviewFeedback).where(InterviewFeedback.interview_id == iv.id))
    who = db.get(User, iv.interviewer_id) if iv.interviewer_id else None
    return InterviewOut(
        id=iv.id, application_id=iv.application_id, candidate_name=cand.full_name, opening_title=app.opening.title,  # type: ignore[union-attr]
        interviewer=InterviewerRef(id=who.id, full_name=who.full_name) if who else None, interview_type=iv.interview_type, mode=iv.mode, status=iv.status,
        scheduled_start=iv.scheduled_start, duration_minutes=iv.duration_minutes, meeting_link=iv.meeting_link, location=iv.location, instructions=iv.instructions, cancel_reason=iv.cancel_reason,
        feedback=FeedbackOut(**{c: getattr(fb, c) for c in ("technical_feedback", "communication_feedback", "strengths", "improvements", "recommendation")},
                             submitted_by=(db.get(User, fb.submitted_by).full_name if fb.submitted_by else None), updated_at=fb.updated_at) if fb else None,
        can_manage=_can_manage(db, user, iv) and iv.status not in (InterviewStatus.COMPLETED, InterviewStatus.CANCELLED),
        can_give_feedback=_can_feedback(db, user, iv) and iv.status in (*UPCOMING, InterviewStatus.COMPLETED),
    )


def _tell_candidate(db: Session, background: BackgroundTasks | None, iv: Interview, kind: str) -> None:
    app = db.get(JobApplication, iv.application_id)
    cand = application_service.applicant_user(db, app)  # type: ignore[arg-type]
    title = app.opening.title  # type: ignore[union-attr]
    verbs = {"scheduled": "An interview has been scheduled", "rescheduled": "Your interview has been rescheduled", "cancelled": "Your interview has been cancelled"}
    head = verbs[kind]
    lines = [f"Hello {cand.full_name},", f"{head} for “{title}”."]
    if kind != "cancelled" and iv.scheduled_start:
        lines.append(f"When: {_fmt(iv.scheduled_start)} ({iv.duration_minutes} minutes). Type: {iv.interview_type.value}; mode: {iv.mode.value}.")
        if iv.meeting_link:
            lines.append(f"Meeting link: {iv.meeting_link}")
        if iv.location:
            lines.append(f"Location: {iv.location}")
        if iv.instructions:
            lines.append(f"Instructions: {iv.instructions}")
    if kind == "cancelled" and iv.cancel_reason:
        lines.append(f"Reason: {iv.cancel_reason}")
    notification_service.notify(db, cand.id, f"interview_{kind}", head, f"{head} for “{title}”." + (f" {_fmt(iv.scheduled_start)}" if kind != "cancelled" and iv.scheduled_start else ""), "/my-interviews")
    email_service.queue_email(db, background, to_email=cand.email, subject=f"{head}: {title}", template=f"interview_{kind}", title=head, paragraphs=lines,
                              button=("View interview details", f"{get_settings().frontend_url.rstrip('/')}/my-interviews"), user_id=cand.id)


def _tell_interviewer(db: Session, iv: Interview, text: str) -> None:
    if iv.interviewer_id:
        notification_service.notify(db, iv.interviewer_id, "interview_assigned", "Interview update", text, f"/interviews/{iv.id}")


def create(db: Session, user: User, data: InterviewCreate, request: Request, background: BackgroundTasks | None) -> Interview:
    _staff(user)
    app = application_service.get_application(db, data.application_id)
    access.require_opening_access(db, user, app.opening_id)
    access.require_perm(db, user, "manage_interviews")
    if app.status != ApplicationStatus.SHORTLISTED:
        raise AppError(409, "not_shortlisted", "Interviews can be scheduled once the candidate has been shortlisted.")
    if data.scheduled_start and data.scheduled_start <= utcnow():
        raise AppError(422, "start_in_past", "The interview must start in the future.", fields={"scheduled_start": "Choose a future time"})
    _interviewer(db, app, data.interviewer_id)
    iv = Interview(application_id=app.id, interviewer_id=data.interviewer_id, interview_type=data.interview_type, mode=data.mode, scheduled_start=data.scheduled_start,
                   duration_minutes=data.duration_minutes, meeting_link=data.meeting_link, location=data.location, instructions=data.instructions, created_by=user.id,
                   status=InterviewStatus.SCHEDULED if data.scheduled_start else InterviewStatus.PENDING)
    db.add(iv)
    db.flush()
    if iv.status == InterviewStatus.SCHEDULED:
        _tell_candidate(db, background, iv, "scheduled")
    _tell_interviewer(db, iv, f"You were assigned an interview for “{app.opening.title}”.")
    audit_service.log_action(db, "interview.created", actor=user, entity_type="interview", entity_id=iv.id, request=request, details={"application_id": app.id})
    db.commit()
    return iv


def update(db: Session, user: User, iv: Interview, data: InterviewUpdate, request: Request, background: BackgroundTasks | None) -> Interview:
    _staff(user)
    if not _can_manage(db, user, iv):
        require_view(db, user, iv)
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
    if iv.status in (InterviewStatus.COMPLETED, InterviewStatus.CANCELLED):
        raise AppError(409, "not_editable", "A completed or cancelled interview cannot be changed.")
    app = db.get(JobApplication, iv.application_id)
    fields = data.model_dump(exclude_unset=True)
    if "interviewer_id" in fields:
        _interviewer(db, app, fields["interviewer_id"])  # type: ignore[arg-type]
    time_changed = "scheduled_start" in fields and fields["scheduled_start"] != iv.scheduled_start
    if time_changed and fields["scheduled_start"] and fields["scheduled_start"] <= utcnow():
        raise AppError(422, "start_in_past", "The interview must start in the future.", fields={"scheduled_start": "Choose a future time"})
    for k, v in fields.items():
        if k in ("interview_type", "mode", "duration_minutes") and v is None:
            continue
        setattr(iv, k, v)
    kind = None
    if time_changed and iv.scheduled_start:
        kind = "scheduled" if iv.status == InterviewStatus.PENDING else "rescheduled"
        iv.status = InterviewStatus.SCHEDULED if kind == "scheduled" else InterviewStatus.RESCHEDULED
    elif fields.keys() & {"meeting_link", "location", "instructions", "duration_minutes", "mode"} and iv.status in UPCOMING:
        kind = "rescheduled"  # details changed: tell the candidate
    if kind:
        _tell_candidate(db, background, iv, kind)
    if "interviewer_id" in fields:
        _tell_interviewer(db, iv, f"You were assigned an interview for “{app.opening.title}”.")  # type: ignore[union-attr]
    audit_service.log_action(db, "interview.updated", actor=user, entity_type="interview", entity_id=iv.id, request=request, details={"fields": sorted(fields)})
    db.commit()
    return iv


def cancel(db: Session, user: User, iv: Interview, reason: str, request: Request, background: BackgroundTasks | None) -> Interview:
    _staff(user)
    if not _can_manage(db, user, iv):
        require_view(db, user, iv)
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
    if iv.status in (InterviewStatus.COMPLETED, InterviewStatus.CANCELLED):
        raise AppError(409, "not_cancellable", "This interview is already completed or cancelled.")
    iv.status, iv.cancel_reason = InterviewStatus.CANCELLED, reason
    _tell_candidate(db, background, iv, "cancelled")
    _tell_interviewer(db, iv, "An interview you were assigned to was cancelled.")
    audit_service.log_action(db, "interview.cancelled", actor=user, entity_type="interview", entity_id=iv.id, request=request, details={"reason": reason})
    db.commit()
    return iv


def complete(db: Session, user: User, iv: Interview, request: Request) -> Interview:
    require_view(db, user, iv)
    if not _can_feedback(db, user, iv):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
    if iv.status not in UPCOMING:
        raise AppError(409, "not_completable", "Only a scheduled interview can be marked complete.")
    iv.status = InterviewStatus.COMPLETED
    audit_service.log_action(db, "interview.completed", actor=user, entity_type="interview", entity_id=iv.id, request=request)
    db.commit()
    return iv


def save_feedback(db: Session, user: User, iv: Interview, data: FeedbackIn, request: Request) -> Interview:
    require_view(db, user, iv)
    if not _can_feedback(db, user, iv):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
    if iv.status not in (*UPCOMING, InterviewStatus.COMPLETED):
        raise AppError(409, "no_feedback_yet", "Feedback can be recorded for a scheduled or completed interview.")
    fb = db.scalar(select(InterviewFeedback).where(InterviewFeedback.interview_id == iv.id))
    if fb is None:
        fb = InterviewFeedback(interview_id=iv.id, **data.model_dump(), submitted_by=user.id)
        db.add(fb)
    else:
        for k, v in data.model_dump().items():
            setattr(fb, k, v)
        fb.submitted_by = user.id
    iv.status = InterviewStatus.COMPLETED
    audit_service.log_action(db, "interview.feedback_saved", actor=user, entity_type="interview", entity_id=iv.id, request=request, details={"recommendation": data.recommendation.value})
    db.commit()
    return iv


def list_interviews(db: Session, user: User, *, status: str | None, application_id: int | None, mine: bool, page: int, page_size: int):
    _staff(user)
    q = select(Interview).join(JobApplication, JobApplication.id == Interview.application_id)
    scope = access.staff_scope(db, user)
    if scope is not None:
        q = q.where(JobApplication.opening_id.in_(scope))
    if mine or not access.has_permission(db, user, "manage_interviews"):
        q = q.where(Interview.interviewer_id == user.id)  # interviewers without the permission only see their own
    if status:
        q = q.where(Interview.status == InterviewStatus(status))
    if application_id:
        q = q.where(Interview.application_id == application_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Interview.scheduled_start.desc().nulls_first(), Interview.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return [out(db, user, r) for r in rows], total


def my_interviews(db: Session, user: User) -> list[MyInterview]:
    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id)) if user.role == Role.APPLICANT else None
    if cp is None:
        raise AppError(404, "not_found", "Not found.")
    rows = db.scalars(select(Interview).join(JobApplication, JobApplication.id == Interview.application_id).where(JobApplication.candidate_id == cp.id)
                      .order_by(Interview.scheduled_start.desc().nulls_first())).all()
    result = []
    for iv in rows:
        app = db.get(JobOpening, db.get(JobApplication, iv.application_id).opening_id)  # type: ignore[union-attr]
        live = iv.status in UPCOMING
        result.append(MyInterview(id=iv.id, opening_title=app.title, interview_type=iv.interview_type, mode=iv.mode, status=iv.status, scheduled_start=iv.scheduled_start,  # type: ignore[union-attr]
                                  duration_minutes=iv.duration_minutes, meeting_link=iv.meeting_link if live else None, location=iv.location if live else None,
                                  instructions=iv.instructions if live else None))
    return result
