from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.api.dependencies.auth import (
    ApplicantUser,
    CurrentUser,
    DbSession,
    ReviewApplications,
)
from app.core.errors import AppError
from app.models import ApplicationStatus, CandidateProfile, Role
from app.schemas.common import make_page
from app.schemas.recruitment import (
    ApplicationDetail,
    ApplicationListItem,
    ApplyRequest,
    HistoryOut,
    MessageRequest,
    OptionalNoteRequest,
    ReasonRequest,
    RespondRequest,
)
from app.services import access
from app.services import application_service as svc

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("", response_model=ApplicationDetail, status_code=201)
def apply(data: ApplyRequest, background: BackgroundTasks, request: Request, user: ApplicantUser, db: DbSession):
    app = svc.apply(db, user, data, background, request)
    return svc.build_detail(db, app, user)


@router.get("")
def list_applications(
    user: CurrentUser, db: DbSession, opening_id: int | None = None, status: ApplicationStatus | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    if user.role == Role.APPLICANT:
        cp = db.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).first()
        items, total = svc.list_applications(db, candidate_id=cp.id if cp else -1, status=status, search=search, page=page, page_size=page_size)
    else:
        access.require_perm(db, user, "review_applications")
        items, total = svc.list_applications(db, opening_ids=access.staff_scope(db, user), opening_id=opening_id, status=status, search=search, page=page, page_size=page_size)
    return make_page([ApplicationListItem(**i) for i in items], total, page, page_size)


def _viewable(db, user, application_id: int):
    app = svc.get_application(db, application_id)
    if user.role == Role.APPLICANT:
        svc.require_owner(db, user, app)
    else:
        svc.require_reviewer(db, user, app)
    return app


@router.get("/{application_id}", response_model=ApplicationDetail)
def detail(application_id: int, user: CurrentUser, db: DbSession):
    return svc.build_detail(db, _viewable(db, user, application_id), user)


@router.get("/{application_id}/history", response_model=list[HistoryOut])
def history(application_id: int, user: CurrentUser, db: DbSession):
    app = _viewable(db, user, application_id)
    return svc.build_history(db, app, for_applicant=user.role == Role.APPLICANT)


# ---- applicant actions


def _own(db, user, application_id: int):
    app = svc.get_application(db, application_id)
    svc.require_owner(db, user, app)
    return app


@router.post("/{application_id}/withdraw", response_model=ApplicationDetail)
def withdraw(application_id: int, request: Request, user: ApplicantUser, db: DbSession):
    return svc.build_detail(db, svc.withdraw(db, _own(db, user, application_id), user, request), user)


@router.post("/{application_id}/respond", response_model=ApplicationDetail)
def respond(application_id: int, data: RespondRequest, request: Request, user: ApplicantUser, db: DbSession):
    return svc.build_detail(db, svc.respond(db, _own(db, user, application_id), user, data.message, data.resume_id, request), user)


# ---- reviewer actions


def _review(db, user, application_id: int):
    app = svc.get_application(db, application_id)
    svc.require_reviewer(db, user, app)
    return app


@router.post("/{application_id}/start-review", response_model=ApplicationDetail)
def start_review(application_id: int, request: Request, user: ReviewApplications, db: DbSession):
    return svc.build_detail(db, svc.start_review(db, _review(db, user, application_id), user, request), user)


@router.post("/{application_id}/approve", response_model=ApplicationDetail)
def approve(application_id: int, data: OptionalNoteRequest, background: BackgroundTasks, request: Request, user: ReviewApplications, db: DbSession):
    return svc.build_detail(db, svc.approve(db, _review(db, user, application_id), user, data.note, background, request), user)


@router.post("/{application_id}/reject", response_model=ApplicationDetail)
def reject(application_id: int, data: ReasonRequest, background: BackgroundTasks, request: Request, user: ReviewApplications, db: DbSession):
    return svc.build_detail(db, svc.reject(db, _review(db, user, application_id), user, data.reason, background, request), user)


@router.post("/{application_id}/request-info", response_model=ApplicationDetail)
def request_info(application_id: int, data: MessageRequest, background: BackgroundTasks, request: Request, user: ReviewApplications, db: DbSession):
    return svc.build_detail(db, svc.request_info(db, _review(db, user, application_id), user, data.message, background, request), user)


@router.post("/{application_id}/comment", response_model=ApplicationDetail)
def comment(application_id: int, data: MessageRequest, request: Request, user: ReviewApplications, db: DbSession):
    """Internal reviewer note. Never shown to the applicant."""
    if not data.message.strip():
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"message": "Enter a comment"})
    return svc.build_detail(db, svc.add_comment(db, _review(db, user, application_id), user, data.message.strip(), request), user)
