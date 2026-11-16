"""Bulk resume screening (staff with the bulk_upload_resumes permission and access to the opening)."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import BulkBatch, JobOpening, User
from app.schemas.bulk import BatchCreated, BatchOut, ItemDetail, ItemOut, TriageIn
from app.schemas.common import make_page
from app.services import audit_service, bulk_service as svc, export_service, storage_service
from app.services.access import staff_scope

router = APIRouter(prefix="/bulk-batches", tags=["Bulk resume screening"])


def _batch_out(db, b: BulkBatch) -> BatchOut:
    o = db.get(JobOpening, b.opening_id)
    u = db.get(User, b.created_by) if b.created_by else None
    return BatchOut(
        id=b.id, name=b.name, opening_id=b.opening_id, opening_title=o.title if o else "", created_by_name=u.full_name if u else None,
        created_at=b.created_at, ai_provider=b.ai_provider, ai_is_mock=b.ai_is_mock, progress=svc.progress(db, b.id),
    )


def _item_out(db, it, opening_id: int, detail: bool = False):
    app_id = svc.existing_application_id(db, it, opening_id)
    data = dict(
        id=it.id, filename=it.filename, size_bytes=it.size_bytes, status=it.status, error=it.error, attempts=it.attempts,
        candidate_name=it.candidate_name, email=it.email, phone=it.phone, skills=it.skills or [], experience_years=it.experience_years,
        match_score=it.match_score, duplicate_kind=it.duplicate_kind, duplicate_of_item_id=it.duplicate_of_item_id,
        existing_applicant=it.existing_candidate_id is not None, existing_application_id=app_id,
        review_status=it.review_status, review_note=it.review_note, warnings=it.warnings or [],
    )
    if detail:
        return ItemDetail(**data, education=it.education or [], analysis=it.analysis)
    return ItemOut(**data)


@router.get("")
def list_batches(
    user: CurrentUser, db: DbSession, opening_id: int | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    svc.require(db, user)
    stmt = select(BulkBatch)
    scope = staff_scope(db, user)
    if scope is not None:
        stmt = stmt.where(BulkBatch.opening_id.in_(scope))
    if opening_id:
        stmt = stmt.where(BulkBatch.opening_id == opening_id)
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(BulkBatch.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return make_page([_batch_out(db, b) for b in rows], total, page, page_size)


@router.post("", response_model=BatchCreated, status_code=202, dependencies=[Depends(rate_limit("bulk_upload", 20, 3600))])
async def create_batch(
    request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession,
    opening_id: int = Form(...), name: str = Form(default=""), files: list[UploadFile] = File(...),
):
    svc.require(db, user, opening_id)
    payload = []
    for f in files:
        payload.append((f.filename or "resume", await f.read()))
    batch, rejected = svc.create_batch(db, user, opening_id, name, payload, request)
    background.add_task(svc.run_batch, batch.id)
    return BatchCreated(batch=_batch_out(db, batch), rejected=rejected)


@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, user: CurrentUser, db: DbSession):
    return _batch_out(db, svc.get_batch(db, user, batch_id))


@router.delete("/{batch_id}", status_code=204)
def delete_batch(batch_id: int, request: Request, user: CurrentUser, db: DbSession):
    svc.delete_batch(db, user, svc.get_batch(db, user, batch_id), request)


@router.post("/{batch_id}/retry")
def retry_failed(batch_id: int, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession, item_id: int | None = None):
    b = svc.get_batch(db, user, batch_id)
    n = svc.retry(db, user, b, item_id, request)
    if n:
        background.add_task(svc.run_batch, b.id)
    return {"requeued": n}


@router.get("/{batch_id}/items")
def list_items(
    batch_id: int, user: CurrentUser, db: DbSession,
    status: Literal["queued", "processing", "done", "failed"] | None = None,
    review_status: Literal["unreviewed", "interesting", "not_suitable"] | None = None,
    duplicates: bool | None = None, min_score: int | None = Query(default=None, ge=0, le=100),
    search: str | None = Query(default=None, max_length=100),
    sort: Literal["score", "name", "filename", "experience", "created"] = "score", desc: bool = True,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
):
    b = svc.get_batch(db, user, batch_id)
    rows, total = svc.list_items(
        db, b.id, status=status, review_status=review_status, duplicates=duplicates, min_score=min_score, search=search,
        sort=sort, desc=desc, page=page, page_size=page_size,
    )
    return make_page([_item_out(db, r, b.opening_id) for r in rows], total, page, page_size)


@router.get("/{batch_id}/export", dependencies=[Depends(rate_limit("bulk_export", 30, 3600))])
def export_items(batch_id: int, request: Request, user: CurrentUser, db: DbSession, format: Literal["csv", "xlsx"] = "csv"):
    b = svc.get_batch(db, user, batch_id)
    rows, _ = svc.list_items(
        db, b.id, status=None, review_status=None, duplicates=None, min_score=None, search=None, sort="score", desc=True, page=1, page_size=100000,
    )
    headers = ["File", "Name (extracted)", "Email", "Phone", "Experience (years)", "Skills", "Match score (advisory)", "Status", "Duplicate", "Triage", "Triage note", "Warnings"]
    data = [
        [r.filename, r.candidate_name, r.email, r.phone, r.experience_years, r.skills or [], r.match_score, r.status.value,
         r.duplicate_kind or "", r.review_status.value, r.review_note or "", r.warnings or []]
        for r in rows
    ]
    audit_service.log_action(db, "bulk_batch.export", actor=user, entity_type="bulk_batch", entity_id=b.id, request=request, details={"format": format, "rows": len(data)})
    db.commit()
    return export_service.respond(format, f"bulk-batch-{b.id}", headers, data, "Screening")


item_router = APIRouter(prefix="/bulk-items", tags=["Bulk resume screening"])


@item_router.get("/{item_id}", response_model=ItemDetail)
def get_item(item_id: int, user: CurrentUser, db: DbSession):
    it, b = svc.get_item(db, user, item_id)
    return _item_out(db, it, b.opening_id, detail=True)


@item_router.put("/{item_id}/triage", response_model=ItemOut)
def triage(item_id: int, data: TriageIn, request: Request, user: CurrentUser, db: DbSession):
    it, b = svc.get_item(db, user, item_id)
    return _item_out(db, svc.triage(db, user, it, data.status, data.note, request), b.opening_id)


@item_router.get("/{item_id}/file")
def download(item_id: int, request: Request, user: CurrentUser, db: DbSession):
    it, _ = svc.get_item(db, user, item_id)
    try:
        path = storage_service.path_for(it.stored_name)
    except ValueError as e:
        raise AppError(404, "not_found", "File not found.") from e
    if not path.exists():
        raise AppError(404, "not_found", "File not found.")
    audit_service.log_action(db, "bulk_item.download", actor=user, entity_type="bulk_item", entity_id=it.id, request=request)
    db.commit()
    media = "application/pdf" if it.filename.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=it.filename, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
