"""Scheduling, invitations, accept and reschedule flows (Phase 5).

Rules enforced here (never only in the UI):
* Only approved applications get a schedule, and only from a *published* assessment version.
* One active schedule per application.
* Invitation links carry a random token that is stored hashed and can only be used by the invited applicant
  while logged in. A forwarded link is useless to anyone else.
* Applicants see their own invitations only (404 for everything else). Employees need `schedule_tests`
  and an assignment to the opening.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    ACTIVE_SCHEDULE_STATUSES,
    Assessment,
    AssessmentSchedule,
    AssessmentVersion,
    ApplicationStatus,
    AttemptAnswer,
    AttemptRecording,
    AttemptStatus,
    CandidateProfile,
    EvaluationResult,
    JobApplication,
    JobOpening,
    RescheduleRequest,
    RescheduleStatus,
    Role,
    ScheduleEvent,
    ScheduleStatus,
    TestAttempt,
    User,
)
from app.models.base import utcnow
from app.schemas.scheduling import (
    AttemptSummary,
    EventOut,
    InvitationOut,
    InvitationSection,
    RescheduleDecision,
    RescheduleIn,
    RescheduleOut,
    ScheduleCreate,
    ScheduleDetail,
    ScheduleListItem,
    ScheduleUpdate,
)
from app.services import access, application_service, audit_service, email_service, notification_service

OPEN_RESCHEDULE = (RescheduleStatus.PENDING, RescheduleStatus.ALTERNATIVE_SUGGESTED)


# ---- helpers -------------------------------------------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    t = secrets.token_urlsafe(32)
    return t, hash_token(t)


def _fmt(dt: datetime) -> str:
    return dt.astimezone().strftime("%d %b %Y, %H:%M %Z")


def log_event(db: Session, sch: AssessmentSchedule, kind: str, *, actor: User | None = None, attempt_id: int | None = None,
              client: bool = False, details: dict | None = None) -> None:
    db.add(ScheduleEvent(schedule_id=sch.id, attempt_id=attempt_id, kind=kind, actor_id=actor.id if actor else None,
                         client_reported=client, details=details))


def get_schedule(db: Session, schedule_id: int) -> AssessmentSchedule:
    s = db.get(AssessmentSchedule, schedule_id)
    if s is None:
        raise AppError(404, "not_found", "Schedule not found.")
    return s


def candidate_profile(db: Session, user: User) -> CandidateProfile:
    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id)) if user.role == Role.APPLICANT else None
    if cp is None:
        raise AppError(404, "not_found", "Not found.")
    return cp


def require_candidate(db: Session, user: User, sch: AssessmentSchedule) -> None:
    cp = candidate_profile(db, user)
    if sch.candidate_id != cp.id:
        raise AppError(404, "not_found", "Test not found.")  # never reveal other people's invitations


def require_staff(db: Session, user: User, sch: AssessmentSchedule | None = None, *, application: JobApplication | None = None) -> JobApplication:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    app = application or application_service.get_application(db, sch.application_id)  # type: ignore[union-attr]
    access.require_opening_access(db, user, app.opening_id)
    access.require_perm(db, user, "schedule_tests")
    return app


def _version(db: Session, sch: AssessmentSchedule) -> AssessmentVersion:
    v = db.get(AssessmentVersion, sch.version_id)
    assert v is not None
    return v


def _total_questions(v: AssessmentVersion) -> int:
    return sum(len(s["questions"]) for s in v.snapshot["sections"])


def _attempt(db: Session, sch: AssessmentSchedule) -> TestAttempt | None:
    return db.scalar(select(TestAttempt).where(TestAttempt.schedule_id == sch.id))


def _link(token: str) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}/test/{token}"


def refresh_status(db: Session, sch: AssessmentSchedule) -> None:
    """Lazy expiry: a missed window becomes `expired` as soon as anyone looks at it."""
    if sch.status in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) and utcnow() > sch.window_end:
        sch.status = ScheduleStatus.EXPIRED
        log_event(db, sch, "expired")
        db.flush()


def expire_missed(db: Session) -> int:
    rows = db.scalars(select(AssessmentSchedule).where(
        AssessmentSchedule.status.in_((ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED)), AssessmentSchedule.window_end < utcnow())).all()
    for s in rows:
        refresh_status(db, s)
    db.commit()
    return len(rows)


def published_version_for(db: Session, application_id: int) -> tuple[Assessment, AssessmentVersion] | None:
    row = db.execute(
        select(Assessment, AssessmentVersion)
        .join(AssessmentVersion, AssessmentVersion.assessment_id == Assessment.id)
        .where(Assessment.application_id == application_id, AssessmentVersion.published_at.is_not(None))
        .order_by(AssessmentVersion.published_at.desc(), AssessmentVersion.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


# ---- staff side ----------------------------------------------------------------------------------

def _send_invitation(db: Session, background: BackgroundTasks | None, sch: AssessmentSchedule, token: str, *, kind: str) -> None:
    app = application_service.get_application(db, sch.application_id)
    user = application_service.applicant_user(db, app)
    opening = db.get(JobOpening, app.opening_id)
    title = opening.title if opening else "your application"
    verb = {"created": "invited to", "resent": "reminded about", "rescheduled": "given a new time for"}[kind]
    notification_service.notify(db, user.id, "test_invitation", "Online assessment scheduled",
                                f"You were {verb} the online assessment for “{title}”. Window: {_fmt(sch.window_start)} to {_fmt(sch.window_end)}.",
                                f"/my-tests/{sch.id}")
    paragraphs = [
        f"Hello {user.full_name},",
        f"You have been invited to complete the online assessment for “{title}”.",
        f"Test window: {_fmt(sch.window_start)} to {_fmt(sch.window_end)}. Duration: {sch.duration_minutes} minutes once you start.",
        "Please accept the invitation, or request a different time, before the window opens. Log in with the account you applied with; the link only works for you.",
        "The test includes a speaking section that records your voice. You will be asked for consent and microphone access before you start. "
        "Use a quiet place, a working microphone and a stable connection. Speak naturally: accents are not penalised.",
    ]
    if sch.instructions:
        paragraphs.append(f"Note from the recruitment team: {sch.instructions}")
    paragraphs.append(f"Need help? Contact {get_settings().support_email}.")
    email_service.queue_email(db, background, to_email=user.email, subject=f"Online assessment for {title}", template="test_invitation",
                              title="Your online assessment", paragraphs=paragraphs, button=("Open your assessment", _link(token)), user_id=user.id)
    log_event(db, sch, f"invitation_{kind}", details={"email": user.email})


def create_schedule(db: Session, user: User, data: ScheduleCreate, request: Request, background: BackgroundTasks | None) -> ScheduleDetail:
    app = application_service.get_application(db, data.application_id)
    require_staff(db, user, application=app)
    if app.status != ApplicationStatus.APPROVED:
        raise AppError(409, "application_not_approved", "Only approved applications can be scheduled for an assessment.")
    found = published_version_for(db, app.id)
    if found is None:
        raise AppError(409, "no_published_assessment", "Publish an approved assessment version for this application first.")
    assessment, version = found
    now = utcnow()
    if data.window_end <= now:
        raise AppError(422, "window_in_past", "The test window must end in the future.", fields={"window_end": "Choose a window that ends in the future."})
    duration = data.duration_minutes or version.duration_minutes
    if (data.window_end - data.window_start) < timedelta(minutes=duration):
        raise AppError(422, "window_too_short", f"The window must be at least as long as the {duration}-minute duration.", fields={"window_end": "Window is shorter than the test duration."})
    expires = data.link_expires_at or data.window_end
    if expires < data.window_start:
        raise AppError(422, "bad_link_expiry", "The link must stay valid until the window opens.", fields={"link_expires_at": "Too early."})
    for s in db.scalars(select(AssessmentSchedule).where(AssessmentSchedule.application_id == app.id, AssessmentSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES))).all():
        refresh_status(db, s)
    if db.scalar(select(func.count()).select_from(AssessmentSchedule).where(AssessmentSchedule.application_id == app.id, AssessmentSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES))):
        raise AppError(409, "schedule_exists", "This application already has an active schedule. Cancel it first or edit it.")
    token, digest = _new_token()
    sch = AssessmentSchedule(application_id=app.id, assessment_id=assessment.id, version_id=version.id, candidate_id=app.candidate_id,
                             window_start=data.window_start, window_end=data.window_end, duration_minutes=duration, instructions=data.instructions,
                             link_expires_at=expires, token_hash=digest, created_by=user.id)
    db.add(sch)
    db.flush()
    log_event(db, sch, "created", actor=user, details={"version": version.version})
    _send_invitation(db, background, sch, token, kind="created")
    audit_service.log_action(db, "schedule.created", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request,
                             details={"application_id": app.id, "version": version.version})
    db.commit()
    out = detail(db, user, sch)
    out.invite_link = _link(token)
    return out


def update_schedule(db: Session, user: User, sch: AssessmentSchedule, data: ScheduleUpdate, request: Request, background: BackgroundTasks | None) -> ScheduleDetail:
    require_staff(db, user, sch)
    refresh_status(db, sch)
    if sch.status not in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) or _attempt(db, sch):
        raise AppError(409, "not_editable", "Only schedules that have not started can be edited.")
    start = data.window_start or sch.window_start
    end = data.window_end or sch.window_end
    duration = data.duration_minutes or sch.duration_minutes
    if end <= utcnow() or end <= start or (end - start) < timedelta(minutes=duration):
        raise AppError(422, "bad_window", "The window must end in the future and be at least as long as the duration.")
    changed = (start, end, duration) != (sch.window_start, sch.window_end, sch.duration_minutes)
    sch.window_start, sch.window_end, sch.duration_minutes = start, end, duration
    if data.instructions is not None:
        sch.instructions = data.instructions or None
    token = None
    if changed:
        sch.status, sch.accepted_at = ScheduleStatus.INVITED, None  # the applicant must confirm the new time
        sch.link_expires_at = max(sch.link_expires_at, end)
        token, sch.token_hash = _new_token()
        _send_invitation(db, background, sch, token, kind="rescheduled")
    log_event(db, sch, "updated", actor=user, details={"window_changed": changed})
    audit_service.log_action(db, "schedule.updated", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request, details={"window_changed": changed})
    db.commit()
    out = detail(db, user, sch)
    if token:
        out.invite_link = _link(token)
    return out


def cancel_schedule(db: Session, user: User, sch: AssessmentSchedule, reason: str, request: Request) -> ScheduleDetail:
    require_staff(db, user, sch)
    refresh_status(db, sch)
    if sch.status not in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED):
        raise AppError(409, "not_cancellable", "Only schedules that have not started can be cancelled.")
    sch.status, sch.cancelled_at, sch.cancel_reason = ScheduleStatus.CANCELLED, utcnow(), reason
    for r in db.scalars(select(RescheduleRequest).where(RescheduleRequest.schedule_id == sch.id, RescheduleRequest.status.in_(OPEN_RESCHEDULE))).all():
        r.status = RescheduleStatus.WITHDRAWN
    app = application_service.get_application(db, sch.application_id)
    applicant = application_service.applicant_user(db, app)
    notification_service.notify(db, applicant.id, "test_cancelled", "Online assessment cancelled", f"Your scheduled assessment was cancelled. Reason: {reason}", "/my-tests")
    log_event(db, sch, "cancelled", actor=user, details={"reason": reason})
    audit_service.log_action(db, "schedule.cancelled", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request, details={"reason": reason})
    db.commit()
    return detail(db, user, sch)


def resend_invitation(db: Session, user: User, sch: AssessmentSchedule, request: Request, background: BackgroundTasks | None) -> ScheduleDetail:
    require_staff(db, user, sch)
    refresh_status(db, sch)
    if sch.status not in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED):
        raise AppError(409, "not_resendable", "Only an upcoming schedule can be resent.")
    token, sch.token_hash = _new_token()  # the previous link stops working
    _send_invitation(db, background, sch, token, kind="resent")
    audit_service.log_action(db, "schedule.resent", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request)
    db.commit()
    out = detail(db, user, sch)
    out.invite_link = _link(token)
    return out


def _rows_query(db: Session, user: User):
    q = (select(AssessmentSchedule, JobApplication, JobOpening, User, Assessment)
         .join(JobApplication, JobApplication.id == AssessmentSchedule.application_id)
         .join(JobOpening, JobOpening.id == JobApplication.opening_id)
         .join(CandidateProfile, CandidateProfile.id == AssessmentSchedule.candidate_id)
         .join(User, User.id == CandidateProfile.user_id)
         .join(Assessment, Assessment.id == AssessmentSchedule.assessment_id))
    scope = access.staff_scope(db, user)
    if scope is not None:
        q = q.where(JobApplication.opening_id.in_(scope))
    return q


def _list_item(db: Session, sch, app, opening, cand_user, assessment) -> ScheduleListItem:
    pending = db.scalar(select(func.count()).select_from(RescheduleRequest).where(RescheduleRequest.schedule_id == sch.id, RescheduleRequest.status == RescheduleStatus.PENDING)) or 0
    att = _attempt(db, sch)
    return ScheduleListItem(id=sch.id, application_id=app.id, candidate_name=cand_user.full_name, opening_title=opening.title, assessment_title=assessment.title,
                            status=sch.status, window_start=sch.window_start, window_end=sch.window_end, duration_minutes=sch.duration_minutes,
                            pending_reschedule=bool(pending), attempt_status=att.status if att else None)


def list_schedules(db: Session, user: User, *, status: str | None, application_id: int | None, search: str | None, page: int, page_size: int):
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    access.require_perm(db, user, "schedule_tests")
    expire_missed(db)
    q = _rows_query(db, user)
    if status:
        q = q.where(AssessmentSchedule.status == ScheduleStatus(status))
    if application_id:
        q = q.where(AssessmentSchedule.application_id == application_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(User.full_name.ilike(like) | JobOpening.title.ilike(like))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(AssessmentSchedule.window_start.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return [_list_item(db, *r) for r in rows], total


def _reschedule_out(r: RescheduleRequest) -> RescheduleOut:
    return RescheduleOut(id=r.id, reason=r.reason, preferred_start=r.preferred_start, status=r.status, comment=r.comment,
                         new_window_start=r.new_window_start, new_window_end=r.new_window_end, created_at=r.created_at, decided_at=r.decided_at)


def _reschedules(db: Session, sch: AssessmentSchedule) -> list[RescheduleOut]:
    return [_reschedule_out(r) for r in db.scalars(select(RescheduleRequest).where(RescheduleRequest.schedule_id == sch.id).order_by(RescheduleRequest.id.desc())).all()]


def attempt_summary(db: Session, sch: AssessmentSchedule) -> AttemptSummary | None:
    att = _attempt(db, sch)
    if att is None:
        return None
    answered = db.scalar(select(func.count()).select_from(AttemptAnswer).where(AttemptAnswer.attempt_id == att.id, AttemptAnswer.selected_index.is_not(None))) or 0
    recs = db.scalar(select(func.count(func.distinct(AttemptRecording.question_id))).where(AttemptRecording.attempt_id == att.id)) or 0
    return AttemptSummary(id=att.id, status=att.status, started_at=att.started_at, deadline_at=att.deadline_at, submitted_at=att.submitted_at,
                          submit_reason=att.submit_reason, answered=answered, total_questions=_total_questions(_version(db, sch)), recordings=recs)


def detail(db: Session, user: User, sch: AssessmentSchedule) -> ScheduleDetail:
    app = application_service.get_application(db, sch.application_id)
    opening = db.get(JobOpening, app.opening_id)
    cand_user = application_service.applicant_user(db, app)
    assessment = db.get(Assessment, sch.assessment_id)
    v = _version(db, sch)
    base = _list_item(db, sch, app, opening, cand_user, assessment)
    events = db.scalars(select(ScheduleEvent).where(ScheduleEvent.schedule_id == sch.id).order_by(ScheduleEvent.id.desc()).limit(200)).all()
    editable = sch.status in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) and _attempt(db, sch) is None
    return ScheduleDetail(
        **base.model_dump(), assessment_id=assessment.id, version=v.version, is_mock=bool(assessment.is_mock), instructions=sch.instructions,
        link_expires_at=sch.link_expires_at, accepted_at=sch.accepted_at, cancelled_at=sch.cancelled_at, cancel_reason=sch.cancel_reason,
        candidate_email=cand_user.email, reschedules=_reschedules(db, sch),
        events=[EventOut(id=e.id, kind=e.kind, client_reported=e.client_reported, details=e.details, created_at=e.created_at) for e in events],
        attempt=attempt_summary(db, sch), can_edit=editable, can_manage=True,
        evaluation_id=db.scalar(select(EvaluationResult.id).join(TestAttempt, TestAttempt.id == EvaluationResult.attempt_id).where(TestAttempt.schedule_id == sch.id)),
    )


def staff_get(db: Session, user: User, schedule_id: int) -> AssessmentSchedule:
    sch = get_schedule(db, schedule_id)
    require_staff(db, user, sch)
    refresh_status(db, sch)
    db.commit()
    return sch


# ---- reschedule decisions (staff) ---------------------------------------------------------------

def decide_reschedule(db: Session, user: User, sch: AssessmentSchedule, request_id: int, data: RescheduleDecision, request: Request,
                      background: BackgroundTasks | None) -> ScheduleDetail:
    require_staff(db, user, sch)
    rr = db.get(RescheduleRequest, request_id)
    if rr is None or rr.schedule_id != sch.id:
        raise AppError(404, "not_found", "Reschedule request not found.")
    if rr.status != RescheduleStatus.PENDING:
        raise AppError(409, "already_decided", "This request has already been handled.")
    refresh_status(db, sch)
    if sch.status not in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) or _attempt(db, sch):
        raise AppError(409, "not_reschedulable", "This schedule can no longer be changed.")
    now = utcnow()
    app = application_service.get_application(db, sch.application_id)
    applicant = application_service.applicant_user(db, app)
    if data.action in ("approve", "suggest"):
        assert data.new_window_start and data.new_window_end
        if data.new_window_end <= now or (data.new_window_end - data.new_window_start) < timedelta(minutes=sch.duration_minutes):
            raise AppError(422, "bad_window", "The new window must end in the future and fit the test duration.")
    rr.decided_by, rr.decided_at, rr.comment = user.id, now, data.comment
    if data.action == "approve":
        rr.status, rr.new_window_start, rr.new_window_end = RescheduleStatus.APPROVED, data.new_window_start, data.new_window_end
        sch.window_start, sch.window_end = data.new_window_start, data.new_window_end
        sch.link_expires_at = max(sch.link_expires_at, sch.window_end)
        title, msg = "Reschedule approved", f"Your new test window: {_fmt(sch.window_start)} to {_fmt(sch.window_end)}."
    elif data.action == "suggest":
        rr.status, rr.new_window_start, rr.new_window_end = RescheduleStatus.ALTERNATIVE_SUGGESTED, data.new_window_start, data.new_window_end
        title, msg = "Alternative time suggested", f"We suggest {_fmt(rr.new_window_start)} to {_fmt(rr.new_window_end)}. Please accept or decline it."  # type: ignore[arg-type]
    else:
        rr.status = RescheduleStatus.REJECTED
        title, msg = "Reschedule request declined", f"Your original window stays in place. {data.comment}"
    notification_service.notify(db, applicant.id, "reschedule_update", title, msg, f"/my-tests/{sch.id}")
    email_service.queue_email(db, background, to_email=applicant.email, subject=title, template="reschedule_update", title=title,
                              paragraphs=[f"Hello {applicant.full_name},", msg], button=("View details", f"{get_settings().frontend_url.rstrip('/')}/my-tests/{sch.id}"), user_id=applicant.id)
    log_event(db, sch, f"reschedule_{rr.status.value}", actor=user, details={"request_id": rr.id})
    audit_service.log_action(db, f"schedule.reschedule_{data.action}", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request, details={"request_id": rr.id})
    db.commit()
    return detail(db, user, sch)


# ---- applicant side -------------------------------------------------------------------------------

def invitation_out(db: Session, sch: AssessmentSchedule) -> InvitationOut:
    refresh_status(db, sch)
    app = application_service.get_application(db, sch.application_id)
    opening = db.get(JobOpening, app.opening_id)
    assessment = db.get(Assessment, sch.assessment_id)
    v = _version(db, sch)
    now = utcnow()
    att = _attempt(db, sch)
    rs = v.snapshot.get("repeat_sentence_settings") or {}
    sections = [InvitationSection(kind=s["kind"], title=s["title"], questions=len(s["questions"])) for s in v.snapshot["sections"]]
    open_req = db.scalar(select(func.count()).select_from(RescheduleRequest).where(RescheduleRequest.schedule_id == sch.id, RescheduleRequest.status.in_(OPEN_RESCHEDULE))) or 0
    can_accept = sch.status == ScheduleStatus.INVITED and now <= sch.window_end and now <= sch.link_expires_at
    reason = None
    can_start = False
    if sch.status == ScheduleStatus.IN_PROGRESS and att and att.status == AttemptStatus.IN_PROGRESS and now <= att.deadline_at + timedelta(seconds=get_settings().submit_grace_seconds):
        can_start = True  # resume
    elif sch.status == ScheduleStatus.ACCEPTED:
        if now < sch.window_start:
            reason = f"The test opens on {_fmt(sch.window_start)}."
        elif now > sch.window_end:
            reason = "The test window has closed."
        else:
            can_start = True
    elif sch.status == ScheduleStatus.INVITED:
        reason = "Accept the invitation first."
    elif sch.status == ScheduleStatus.EXPIRED:
        reason = "The test window has closed. Contact the recruitment team."
    elif sch.status == ScheduleStatus.CANCELLED:
        reason = "This test was cancelled."
    elif sch.status == ScheduleStatus.COMPLETED:
        reason = "You have already submitted this test."
    can_resched = sch.status in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) and now < sch.window_start and not open_req and att is None
    has_rs = any(s["kind"] == "repeat_sentence" and s["questions"] for s in v.snapshot["sections"])
    return InvitationOut(
        id=sch.id, application_id=app.id, opening_title=opening.title if opening else "", assessment_title=assessment.title if assessment else "",
        status=sch.status, window_start=sch.window_start, window_end=sch.window_end, duration_minutes=sch.duration_minutes, instructions=sch.instructions,
        link_expires_at=sch.link_expires_at, sections=sections, has_repeat_sentence=has_rs, rs_max_replays=rs.get("rs_max_replays"),
        rs_max_attempts=rs.get("rs_max_attempts"), rs_record_seconds=rs.get("rs_record_seconds"), can_accept=can_accept, can_start=can_start,
        start_blocked_reason=None if can_start else reason, can_request_reschedule=can_resched, attempt_id=att.id if att else None,
        reschedules=_reschedules(db, sch), server_now=now,
    )


def my_invitations(db: Session, user: User) -> list[InvitationOut]:
    cp = candidate_profile(db, user)
    rows = db.scalars(select(AssessmentSchedule).where(AssessmentSchedule.candidate_id == cp.id).order_by(AssessmentSchedule.window_start.desc())).all()
    out = [invitation_out(db, s) for s in rows]
    db.commit()
    return out


def my_invitation(db: Session, user: User, schedule_id: int) -> AssessmentSchedule:
    sch = get_schedule(db, schedule_id)
    require_candidate(db, user, sch)
    return sch


def by_token(db: Session, user: User, token: str) -> AssessmentSchedule:
    sch = db.scalar(select(AssessmentSchedule).where(AssessmentSchedule.token_hash == hash_token(token)))
    if sch is None:
        raise AppError(404, "not_found", "This invitation link is not valid.")
    require_candidate(db, user, sch)  # a forwarded link does nothing for another account
    if sch.status in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED) and utcnow() > sch.link_expires_at:
        raise AppError(410, "link_expired", "This invitation link has expired. Please contact the recruitment team.")
    log_event(db, sch, "link_opened", actor=user)
    db.commit()
    return sch


def accept(db: Session, user: User, sch: AssessmentSchedule, request: Request) -> AssessmentSchedule:
    require_candidate(db, user, sch)
    refresh_status(db, sch)
    if sch.status == ScheduleStatus.ACCEPTED:
        return sch  # idempotent
    if sch.status != ScheduleStatus.INVITED:
        raise AppError(409, "not_acceptable", "This invitation can no longer be accepted.")
    if utcnow() > sch.link_expires_at:
        raise AppError(410, "link_expired", "This invitation has expired. Please contact the recruitment team.")
    sch.status, sch.accepted_at = ScheduleStatus.ACCEPTED, utcnow()
    log_event(db, sch, "accepted", actor=user)
    audit_service.log_action(db, "schedule.accepted", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request)
    if sch.created_by:
        notification_service.notify(db, sch.created_by, "test_accepted", "Assessment accepted", f"{user.full_name} accepted the assessment invitation.", f"/schedules/{sch.id}")
    db.commit()
    return sch


def request_reschedule(db: Session, user: User, sch: AssessmentSchedule, data: RescheduleIn, request: Request) -> AssessmentSchedule:
    require_candidate(db, user, sch)
    refresh_status(db, sch)
    inv = invitation_out(db, sch)
    if not inv.can_request_reschedule:
        raise AppError(409, "not_reschedulable", "A reschedule cannot be requested now (the test has started, closed, or a request is already open).")
    rr = RescheduleRequest(schedule_id=sch.id, requested_by=user.id, reason=data.reason, preferred_start=data.preferred_start)
    db.add(rr)
    db.flush()
    log_event(db, sch, "reschedule_requested", actor=user, details={"request_id": rr.id})
    audit_service.log_action(db, "schedule.reschedule_requested", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request, details={"request_id": rr.id})
    targets = [sch.created_by] if sch.created_by else []
    for t in {*targets, *(u.id for u in notification_service.active_admins(db))}:
        notification_service.notify(db, t, "reschedule_requested", "Reschedule requested", f"{user.full_name} asked to reschedule their assessment: {data.reason}", f"/schedules/{sch.id}")
    db.commit()
    return sch


def respond_alternative(db: Session, user: User, sch: AssessmentSchedule, request_id: int, accept_it: bool, request: Request) -> AssessmentSchedule:
    require_candidate(db, user, sch)
    refresh_status(db, sch)
    rr = db.get(RescheduleRequest, request_id)
    if rr is None or rr.schedule_id != sch.id:
        raise AppError(404, "not_found", "Request not found.")
    if rr.status != RescheduleStatus.ALTERNATIVE_SUGGESTED or not (rr.new_window_start and rr.new_window_end):
        raise AppError(409, "not_respondable", "There is no suggested time to respond to.")
    if sch.status not in (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED):
        raise AppError(409, "not_reschedulable", "This schedule can no longer be changed.")
    if accept_it:
        if rr.new_window_end <= utcnow():
            raise AppError(409, "window_passed", "The suggested time has already passed. Please request a new time.")
        rr.status = RescheduleStatus.ALTERNATIVE_ACCEPTED
        sch.window_start, sch.window_end = rr.new_window_start, rr.new_window_end
        sch.link_expires_at = max(sch.link_expires_at, sch.window_end)
    else:
        rr.status = RescheduleStatus.ALTERNATIVE_DECLINED
    log_event(db, sch, f"reschedule_{rr.status.value}", actor=user, details={"request_id": rr.id})
    audit_service.log_action(db, f"schedule.alternative_{'accepted' if accept_it else 'declined'}", actor=user, entity_type="assessment_schedule", entity_id=sch.id, request=request)
    if sch.created_by:
        notification_service.notify(db, sch.created_by, "reschedule_response", "Suggested time answered",
                                    f"{user.full_name} {'accepted' if accept_it else 'declined'} the suggested time.", f"/schedules/{sch.id}")
    db.commit()
    return sch
