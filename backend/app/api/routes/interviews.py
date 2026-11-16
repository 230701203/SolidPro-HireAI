"""Interview management (staff) and the applicant's own interview list."""

from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.api.dependencies.auth import CurrentUser, DbSession
from app.schemas.common import Page, make_page
from app.schemas.interview import CancelIn, FeedbackIn, InterviewCreate, InterviewOut, InterviewUpdate, MyInterview
from app.services import interview_service as svc

router = APIRouter(tags=["Interviews"])


@router.get("/interviews", response_model=Page[InterviewOut])
def list_interviews(user: CurrentUser, db: DbSession, status: str | None = None, application_id: int | None = None, mine: bool = False,
                    page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=100)):
    items, total = svc.list_interviews(db, user, status=status, application_id=application_id, mine=mine, page=page, page_size=page_size)
    return make_page(items, total, page, page_size)


@router.post("/interviews", response_model=InterviewOut, status_code=201)
def create(data: InterviewCreate, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.out(db, user, svc.create(db, user, data, request, background))


@router.get("/interviews/{interview_id}", response_model=InterviewOut)
def get_one(interview_id: int, user: CurrentUser, db: DbSession):
    iv = svc.get_interview(db, interview_id)
    svc.require_view(db, user, iv)
    return svc.out(db, user, iv)


@router.patch("/interviews/{interview_id}", response_model=InterviewOut)
def update(interview_id: int, data: InterviewUpdate, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.out(db, user, svc.update(db, user, svc.get_interview(db, interview_id), data, request, background))


@router.post("/interviews/{interview_id}/cancel", response_model=InterviewOut)
def cancel(interview_id: int, data: CancelIn, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.out(db, user, svc.cancel(db, user, svc.get_interview(db, interview_id), data.reason, request, background))


@router.post("/interviews/{interview_id}/complete", response_model=InterviewOut)
def complete(interview_id: int, request: Request, user: CurrentUser, db: DbSession):
    return svc.out(db, user, svc.complete(db, user, svc.get_interview(db, interview_id), request))


@router.put("/interviews/{interview_id}/feedback", response_model=InterviewOut)
def feedback(interview_id: int, data: FeedbackIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.out(db, user, svc.save_feedback(db, user, svc.get_interview(db, interview_id), data, request))


@router.get("/my-interviews", response_model=list[MyInterview])
def my_interviews(user: CurrentUser, db: DbSession):
    return svc.my_interviews(db, user)
