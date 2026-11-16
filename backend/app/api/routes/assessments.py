"""AI-assisted assessment drafts, human review, approval and immutable versions (staff only)."""

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import Role
from app.schemas.assessment import (
    ApproveRequest, AssessmentDetail, AssessmentListItem, AssessmentUpdate, FromBankRequest, GenerateRequest, QuestionCreate,
    RejectRequest, QuestionUpdate, VersionDetail,
)
from app.schemas.common import Page, make_page
from app.services import assessment_service as svc

router = APIRouter(prefix="/assessments", tags=["Assessments"])


def _staff(user) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")  # applicants must not learn that this area exists


def _load(db, user, assessment_id: int, *, mode: str = "view"):
    _staff(user)
    a = svc.get_assessment(db, assessment_id)
    (svc.require_edit if mode == "edit" else svc.require_view)(db, user, a)
    return a


@router.get("", response_model=Page[AssessmentListItem])
def list_assessments(user: CurrentUser, db: DbSession, status: str | None = None, opening_id: int | None = None, application_id: int | None = None, search: str | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=100)):
    _staff(user)
    items, total = svc.list_assessments(db, user, status=status, opening_id=opening_id, application_id=application_id, search=search, page=page, page_size=page_size)
    return make_page(items, total, page, page_size)


@router.post("", response_model=AssessmentDetail, status_code=201, dependencies=[Depends(rate_limit("ai_assessment", 20, 3600))])
def generate(data: GenerateRequest, request: Request, user: CurrentUser, db: DbSession):
    _staff(user)
    return svc.detail(db, user, svc.generate(db, user, data, request))


@router.get("/{assessment_id}", response_model=AssessmentDetail)
def get_one(assessment_id: int, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, _load(db, user, assessment_id))


@router.patch("/{assessment_id}", response_model=AssessmentDetail)
def update(assessment_id: int, data: AssessmentUpdate, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    return svc.detail(db, user, svc.update_assessment(db, user, a, data, request))


@router.delete("/{assessment_id}", status_code=204)
def delete(assessment_id: int, request: Request, user: CurrentUser, db: DbSession):
    svc.delete_assessment(db, user, _load(db, user, assessment_id, mode="edit"), request)


@router.post("/{assessment_id}/questions", response_model=AssessmentDetail, status_code=201)
def add_question(assessment_id: int, data: QuestionCreate, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.add_question(db, user, a, data, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/questions/from-bank", response_model=AssessmentDetail, status_code=201)
def add_from_bank(assessment_id: int, data: FromBankRequest, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.add_from_bank(db, user, a, data.bank_question_id, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/questions/approve-all", response_model=AssessmentDetail)
def approve_all(assessment_id: int, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.approve_all_questions(db, user, a, request)
    return svc.detail(db, user, a)


@router.patch("/{assessment_id}/questions/{question_id}", response_model=AssessmentDetail)
def edit_question(assessment_id: int, question_id: int, data: QuestionUpdate, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.update_question(db, user, a, question_id, data, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/questions/{question_id}/approve", response_model=AssessmentDetail)
def approve_question(assessment_id: int, question_id: int, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.approve_question(db, user, a, question_id, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/questions/{question_id}/reject", response_model=AssessmentDetail)
def reject_question(assessment_id: int, question_id: int, data: RejectRequest, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.reject_question(db, user, a, question_id, data.reason, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/questions/{question_id}/regenerate", response_model=AssessmentDetail, dependencies=[Depends(rate_limit("ai_assessment", 20, 3600))])
def regenerate_question(assessment_id: int, question_id: int, request: Request, user: CurrentUser, db: DbSession):
    _staff(user)
    a = svc.get_assessment(db, assessment_id)
    svc.require_generate(db, user, a)
    svc.regenerate_question(db, user, a, question_id, request)
    return svc.detail(db, user, a)


@router.delete("/{assessment_id}/questions/{question_id}", response_model=AssessmentDetail)
def delete_question(assessment_id: int, question_id: int, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.delete_question(db, user, a, question_id, request)
    return svc.detail(db, user, a)


@router.post("/{assessment_id}/approve", response_model=AssessmentDetail)
def approve(assessment_id: int, data: ApproveRequest, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.approve_assessment(db, user, a, data.note, request)
    return svc.detail(db, user, a)


@router.get("/{assessment_id}/versions/{version}", response_model=VersionDetail)
def get_version(assessment_id: int, version: int, user: CurrentUser, db: DbSession):
    _staff(user)
    return svc.version_detail(db, user, svc.get_assessment(db, assessment_id), version)


@router.post("/{assessment_id}/versions/{version}/publish", response_model=AssessmentDetail)
def publish(assessment_id: int, version: int, request: Request, user: CurrentUser, db: DbSession):
    a = _load(db, user, assessment_id, mode="edit")
    svc.publish_version(db, user, a, version, request)
    return svc.detail(db, user, a)
