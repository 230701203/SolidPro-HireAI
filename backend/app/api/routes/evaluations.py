"""Results review (staff) and released results (applicant)."""

from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.api.dependencies.auth import CurrentUser, DbSession
from app.schemas.common import Page, make_page
from app.schemas.evaluation import (
    CommentIn, ConfirmIn, DecisionIn, EvaluationDetail, EvaluationListItem, MyResult, OverrideIn, ReasonIn, ReleaseIn,
)
from app.schemas.recruitment import ApplicationDetail
from app.services import application_service as app_svc
from app.services import evaluation_service as svc

router = APIRouter(tags=["Evaluation"])


@router.get("/evaluations", response_model=Page[EvaluationListItem])
def list_evaluations(user: CurrentUser, db: DbSession, status: str | None = None, released: bool | None = None, needs_review: bool | None = None, search: str | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=100)):
    items, total = svc.list_evaluations(db, user, status=status, released=released, needs_review=needs_review, search=search, page=page, page_size=page_size)
    return make_page(items, total, page, page_size)


@router.post("/schedules/{schedule_id}/evaluation", response_model=EvaluationDetail)
def ensure_evaluation(schedule_id: int, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    """Idempotent: creates the evaluation for a submitted test if it does not exist yet."""
    ev = svc.ensure_for_schedule(db, user, schedule_id)
    background.add_task(svc.process_speech_for_attempt, ev.attempt_id)
    return svc.detail(db, user, ev)


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetail)
def get_one(evaluation_id: int, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.staff_get(db, user, evaluation_id))


@router.post("/evaluations/{evaluation_id}/items/{item_id}/override", response_model=EvaluationDetail)
def override(evaluation_id: int, item_id: int, data: OverrideIn, request: Request, user: CurrentUser, db: DbSession):
    ev = svc.override_item(db, user, svc.staff_get(db, user, evaluation_id), item_id, data.marks, data.reason, request)
    return svc.detail(db, user, ev)


@router.post("/evaluations/{evaluation_id}/items/{item_id}/confirm", response_model=EvaluationDetail)
def confirm(evaluation_id: int, item_id: int, data: ConfirmIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.confirm_item(db, user, svc.staff_get(db, user, evaluation_id), item_id, data.note, request))


@router.post("/evaluations/{evaluation_id}/comments", response_model=EvaluationDetail, status_code=201)
def comment(evaluation_id: int, data: CommentIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.add_comment(db, user, svc.staff_get(db, user, evaluation_id), data.body, request))


@router.post("/evaluations/{evaluation_id}/rerun-speech", response_model=EvaluationDetail)
def rerun(evaluation_id: int, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.rerun_speech(db, user, svc.staff_get(db, user, evaluation_id), request))


@router.post("/evaluations/{evaluation_id}/finalize", response_model=EvaluationDetail)
def finalize(evaluation_id: int, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.finalize(db, user, svc.staff_get(db, user, evaluation_id), request))


@router.post("/evaluations/{evaluation_id}/reopen", response_model=EvaluationDetail)
def reopen(evaluation_id: int, data: ReasonIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.reopen(db, user, svc.staff_get(db, user, evaluation_id), data.reason, request))


@router.post("/evaluations/{evaluation_id}/release", response_model=EvaluationDetail)
def release(evaluation_id: int, data: ReleaseIn, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.release(db, user, svc.staff_get(db, user, evaluation_id), data.feedback, request, background))


@router.post("/evaluations/{evaluation_id}/withdraw-release", response_model=EvaluationDetail)
def withdraw(evaluation_id: int, data: ReasonIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.unrelease(db, user, svc.staff_get(db, user, evaluation_id), data.reason, request))


@router.post("/applications/{application_id}/decision", response_model=ApplicationDetail)
def decision(application_id: int, data: DecisionIn, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    app = svc.decide(db, user, application_id, data.decision, data.reason, request, background)
    return app_svc.build_detail(db, app, user)


@router.get("/my-results", response_model=list[MyResult])
def my_results(user: CurrentUser, db: DbSession):
    return svc.my_results(db, user)


@router.get("/my-results/{evaluation_id}", response_model=MyResult)
def my_result(evaluation_id: int, user: CurrentUser, db: DbSession):
    return svc.my_result(db, user, evaluation_id)
