"""Reusable aptitude question bank maintained by staff."""

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import Role
from app.schemas.assessment import BankCreate, BankOut, ImportResult, BankQuestionIn, BankQuestionOut, BankQuestionUpdate, BankUpdate
from app.schemas.common import Page, make_page
from app.services import access
from app.services import question_bank_service as svc
from app.services import question_import_service as importer

router = APIRouter(prefix="/question-banks", tags=["Question bank"])


def _read(user, db) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    if not any(access.has_permission(db, user, c) for c in ("manage_question_bank", "generate_assessments", "approve_assessments")):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")


def _manage(user, db) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    access.require_perm(db, user, "manage_question_bank")


@router.get("", response_model=list[BankOut])
def list_banks(user: CurrentUser, db: DbSession):
    _read(user, db)
    return svc.list_banks(db)


@router.get("/import-template")
def import_template(user: CurrentUser, db: DbSession):
    """Blank Excel file with the expected columns, dropdowns and an instructions sheet."""
    _manage(user, db)
    return Response(importer.template_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="question-import-template.xlsx"', "Cache-Control": "no-store"})


@router.post("", response_model=BankOut, status_code=201)
def create_bank(data: BankCreate, request: Request, user: CurrentUser, db: DbSession):
    _manage(user, db)
    return svc.create_bank(db, user, data, request)


@router.patch("/{bank_id}", response_model=BankOut)
def update_bank(bank_id: int, data: BankUpdate, request: Request, user: CurrentUser, db: DbSession):
    _manage(user, db)
    return svc.update_bank(db, user, bank_id, data, request)


@router.get("/{bank_id}/questions", response_model=Page[BankQuestionOut])
def list_questions(bank_id: int, user: CurrentUser, db: DbSession, topic: str | None = None, difficulty: str | None = None, active: bool | None = None,
                   search: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    _read(user, db)
    items, total = svc.list_questions(db, bank_id, topic=topic, difficulty=difficulty, active=active, search=search, page=page, page_size=page_size)
    return make_page(items, total, page, page_size)


@router.post("/{bank_id}/questions", response_model=BankQuestionOut, status_code=201)
def create_question(bank_id: int, data: BankQuestionIn, request: Request, user: CurrentUser, db: DbSession):
    _manage(user, db)
    return svc.create_question(db, user, bank_id, data, request)


@router.patch("/{bank_id}/questions/{question_id}", response_model=BankQuestionOut)
def update_question(bank_id: int, question_id: int, data: BankQuestionUpdate, request: Request, user: CurrentUser, db: DbSession):
    _manage(user, db)
    return svc.update_question(db, user, bank_id, question_id, data, request)


@router.post("/{bank_id}/import", response_model=ImportResult, dependencies=[Depends(rate_limit("question_import", 30, 3600))])
def import_questions(bank_id: int, request: Request, user: CurrentUser, db: DbSession, file: UploadFile = File(...), dry_run: bool = Query(True)):
    """Check (dry_run=true, the default) or import questions from an .xlsx file. Valid rows are added; others are reported."""
    _manage(user, db)
    bank = svc._get_bank(db, bank_id)
    data = file.file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)  # never read more than the limit + 1 byte
    return importer.import_questions(db, user, bank, data, file.filename or "questions.xlsx", dry_run=dry_run, request=request)
