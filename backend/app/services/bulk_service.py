"""Bulk resume screening (Phase 7).

* Screening only: no accounts are created and no applicant profile is changed.
* Files are validated, stored privately and queued; processing runs in the background with per-file commits,
  so one bad file never blocks the rest, and a crash can be resumed by the sweeper.
* Extracted fields are heuristics, AI scores are advisory, and the triage status has no effect on any applicant.
"""

import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.ai.factory import get_provider
from app.ai.schemas import PROMPT_VERSION, AIProviderError, AnalysisInput
from app.core.config import get_settings
from app.core.errors import AppError
from app.database import SessionLocal
from app.models import (
    BulkBatch,
    BulkItem,
    BulkItemStatus,
    CandidateProfile,
    JobApplication,
    JobOpening,
    Role,
    ScreeningStatus,
    User,
)
from app.models.base import utcnow
from app.services import access, audit_service, document_service, notification_service, resume_extract, storage_service
from app.services.analysis_service import INJECTION_NOTE, INJECTION_PATTERNS

log = logging.getLogger("hireai.bulk")
STALE_AFTER = timedelta(minutes=10)


def require(db: Session, user: User, opening_id: int | None = None) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    access.require_perm(db, user, "bulk_upload_resumes")
    if opening_id is not None:
        access.require_opening_access(db, user, opening_id)


def get_batch(db: Session, user: User, batch_id: int) -> BulkBatch:
    b = db.get(BulkBatch, batch_id)
    if b is None:
        raise AppError(404, "not_found", "Batch not found.")
    require(db, user, b.opening_id)
    return b


def get_item(db: Session, user: User, item_id: int) -> tuple[BulkItem, BulkBatch]:
    it = db.get(BulkItem, item_id)
    if it is None:
        raise AppError(404, "not_found", "Resume not found.")
    return it, get_batch(db, user, it.batch_id)


def _cheap_validate(filename: str, data: bytes) -> str | None:
    s = get_settings()
    ext = Path(filename or "").suffix.lower()
    if ext not in (".pdf", ".docx"):
        return "Only PDF and DOCX files are accepted."
    if not data:
        return "The file is empty."
    if len(data) > s.max_upload_mb * 1024 * 1024:
        return f"Larger than the {s.max_upload_mb} MB limit."
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        return "Not a valid PDF."
    if ext == ".docx" and not data.startswith(b"PK"):
        return "Not a valid DOCX."
    return None


def create_batch(
    db: Session, user: User, opening_id: int, name: str, files: list[tuple[str, bytes]], request: Request
) -> tuple[BulkBatch, list[dict]]:
    require(db, user, opening_id)
    opening = db.get(JobOpening, opening_id)
    if opening is None:
        raise AppError(404, "not_found", "Opening not found.")
    s = get_settings()
    if not files:
        raise AppError(422, "no_files", "Choose at least one resume.")
    if len(files) > s.bulk_max_files:
        raise AppError(422, "too_many_files", f"A batch can hold at most {s.bulk_max_files} resumes.")
    try:
        provider = get_provider()
    except AIProviderError as e:
        raise AppError(503, "ai_unavailable", str(e)) from e

    batch = BulkBatch(
        opening_id=opening_id, created_by=user.id, name=(name or "").strip()[:150] or f"Batch {utcnow():%Y-%m-%d %H:%M}",
        ai_provider=provider.name, ai_is_mock=provider.is_mock,
    )
    db.add(batch)
    db.flush()
    rejected: list[dict] = []
    accepted = 0
    for raw_name, data in files:
        fname = document_service.safe_filename(raw_name)
        problem = _cheap_validate(fname, data)
        if problem:
            rejected.append({"filename": fname, "reason": problem})
            continue
        db.add(BulkItem(
            batch_id=batch.id, filename=fname, stored_name=storage_service.save_bytes(data), size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), status=BulkItemStatus.QUEUED,
        ))
        accepted += 1
    if accepted == 0:
        db.rollback()
        raise AppError(422, "no_valid_files", "None of the files could be accepted.", fields={"files": [r["filename"] + ": " + r["reason"] for r in rejected]})
    audit_service.log_action(
        db, "bulk_batch.create", actor=user, entity_type="bulk_batch", entity_id=batch.id, request=request,
        details={"opening_id": opening_id, "accepted": accepted, "rejected": len(rejected), "provider": provider.name, "mock": provider.is_mock},
    )
    db.commit()
    return batch, rejected


# ---- processing ----------------------------------------------------------------------------------

def _vocabulary(opening: JobOpening) -> list[str]:
    return [*(opening.required_skills or []), *(opening.preferred_skills or [])]


def _mark_duplicates(db: Session, item: BulkItem) -> None:
    item.duplicate_kind = None
    item.existing_candidate_id = None
    item.duplicate_of_item_id = None
    same_file = db.scalar(
        select(BulkItem.id).where(BulkItem.batch_id == item.batch_id, BulkItem.sha256 == item.sha256, BulkItem.id < item.id).order_by(BulkItem.id)
    )
    if same_file:
        item.duplicate_kind, item.duplicate_of_item_id = "duplicate_file", same_file
        return
    if not item.email:
        return
    earlier = db.scalar(
        select(BulkItem.id).where(BulkItem.batch_id == item.batch_id, BulkItem.email == item.email, BulkItem.id < item.id).order_by(BulkItem.id)
    )
    if earlier:
        item.duplicate_kind, item.duplicate_of_item_id = "duplicate_in_batch", earlier
        return
    cand = db.scalar(
        select(CandidateProfile.id).join(User, User.id == CandidateProfile.user_id).where(func.lower(User.email) == item.email)
    )
    if cand:
        item.duplicate_kind, item.existing_candidate_id = "existing_applicant", cand


def process_item(db: Session, item: BulkItem) -> None:
    """Parse, extract, de-duplicate and analyse one file. Raises on failure; the caller records it."""
    batch = db.get(BulkBatch, item.batch_id)
    opening = db.get(JobOpening, batch.opening_id)
    data = storage_service.path_for(item.stored_name).read_bytes()
    parsed = document_service.validate_and_extract(item.filename, data)
    ex = resume_extract.extract(parsed.text, _vocabulary(opening))
    item.candidate_name, item.email, item.phone = ex.candidate_name, ex.email, ex.phone
    item.skills, item.experience_years, item.education = ex.skills, ex.experience_years, ex.education
    warnings = list(ex.warnings)
    _mark_duplicates(db, item)

    text = parsed.text.strip()
    if not text:
        item.match_score, item.analysis = None, None
        warnings.append("No readable text, so no AI analysis was run.")
    else:
        suspicious = bool(INJECTION_PATTERNS.search(text))
        provider = get_provider()
        result = provider.analyze_resume(AnalysisInput(
            job_title=opening.title, job_description=opening.description, required_skills=list(opening.required_skills or []),
            preferred_skills=list(opening.preferred_skills or []), required_qualifications=opening.required_qualifications,
            required_experience=opening.required_experience, candidate_experience_years=ex.experience_years,
            candidate_education=[{"degree": e, "department": None, "graduation_year": None} for e in ex.education],
            candidate_skills=ex.skills, resume_text=text[: get_settings().ai_max_resume_chars],
        ))
        if suspicious:
            result.clarifications_to_verify.insert(0, INJECTION_NOTE)
            warnings.append(INJECTION_NOTE)
        item.match_score = result.match_score
        item.analysis = {**result.model_dump(), "provider": provider.name, "mock": provider.is_mock, "prompt_version": PROMPT_VERSION}
    item.warnings = warnings
    item.error = None
    item.status = BulkItemStatus.DONE
    item.processed_at = utcnow()


def _claim(db: Session, batch_id: int | None = None) -> BulkItem | None:
    stmt = select(BulkItem).where(BulkItem.status == BulkItemStatus.QUEUED, BulkItem.attempts < get_settings().bulk_max_attempts)
    if batch_id is not None:
        stmt = stmt.where(BulkItem.batch_id == batch_id)
    item = db.scalar(stmt.order_by(BulkItem.id).limit(1).with_for_update(skip_locked=True))
    if item is None:
        db.rollback()
        return None
    item.status = BulkItemStatus.PROCESSING
    item.attempts += 1
    db.commit()
    return item


def _run_one(db: Session, item: BulkItem) -> None:
    try:
        process_item(db, item)
        db.commit()
    except Exception as exc:  # one bad file must not stop the batch
        db.rollback()
        item = db.get(BulkItem, item.id)
        msg = exc.message if isinstance(exc, AppError) else (str(exc) or exc.__class__.__name__)
        retry = not isinstance(exc, AppError) and item.attempts < get_settings().bulk_max_attempts
        item.status = BulkItemStatus.QUEUED if retry else BulkItemStatus.FAILED
        item.error = str(msg)[:500]
        if not retry:
            item.processed_at = utcnow()
        db.commit()
        log.warning("bulk item %s failed (attempt %s): %s", item.id, item.attempts, msg)


def _notify_if_finished(db: Session, batch_id: int) -> None:
    """Tell the uploader once nothing in the batch is queued or processing any more (in-app only, no email)."""
    batch = db.get(BulkBatch, batch_id)
    if batch is None or batch.created_by is None:
        return
    p = progress(db, batch_id)
    if not p["complete"]:
        return
    msg = f"“{batch.name}”: {p['done']} of {p['total']} resumes screened" + (f", {p['failed']} failed (you can retry them)." if p["failed"] else ".")
    notification_service.notify(db, batch.created_by, "bulk_batch_complete", "Bulk screening finished", msg, f"/bulk/{batch_id}")
    db.commit()


def run_batch(batch_id: int) -> int:
    """Background entry point. Uses its own session."""
    done = 0
    with SessionLocal() as db:
        while (item := _claim(db, batch_id)) is not None:
            _run_one(db, item)
            _notify_if_finished(db, batch_id)
            done += 1
    return done


def sweep(db: Session, limit: int = 20) -> dict:
    """Recover items stuck in 'processing' (crash) and work through leftovers."""
    cutoff = utcnow() - STALE_AFTER
    reset = db.execute(
        update(BulkItem).where(BulkItem.status == BulkItemStatus.PROCESSING, BulkItem.updated_at < cutoff).values(status=BulkItemStatus.QUEUED)
    ).rowcount
    db.commit()
    processed = 0
    while processed < limit and (item := _claim(db)) is not None:
        _run_one(db, item)
        _notify_if_finished(db, item.batch_id)
        processed += 1
    return {"bulk_recovered": reset or 0, "bulk_processed": processed}


# ---- reads and actions ---------------------------------------------------------------------------

def progress(db: Session, batch_id: int) -> dict:
    rows = dict(db.execute(select(BulkItem.status, func.count()).where(BulkItem.batch_id == batch_id).group_by(BulkItem.status)).all())
    counts = {st.value: int(rows.get(st, 0)) for st in BulkItemStatus}
    total = sum(counts.values())
    finished = counts["done"] + counts["failed"]
    return {**counts, "total": total, "finished": finished, "complete": total > 0 and finished == total}


SORTS = {
    "score": BulkItem.match_score, "name": BulkItem.candidate_name, "filename": BulkItem.filename,
    "experience": BulkItem.experience_years, "created": BulkItem.id,
}


def list_items(
    db: Session, batch_id: int, *, status: str | None, review_status: str | None, duplicates: bool | None,
    min_score: int | None, search: str | None, sort: str, desc: bool, page: int, page_size: int,
):
    stmt = select(BulkItem).where(BulkItem.batch_id == batch_id)
    if status:
        stmt = stmt.where(BulkItem.status == status)
    if review_status:
        stmt = stmt.where(BulkItem.review_status == review_status)
    if duplicates is True:
        stmt = stmt.where(BulkItem.duplicate_kind.is_not(None))
    elif duplicates is False:
        stmt = stmt.where(BulkItem.duplicate_kind.is_(None))
    if min_score is not None:
        stmt = stmt.where(BulkItem.match_score >= min_score)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(BulkItem.candidate_name.ilike(like), BulkItem.email.ilike(like), BulkItem.filename.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTS.get(sort, BulkItem.match_score)
    order = col.desc().nulls_last() if desc else col.asc().nulls_last()
    rows = db.scalars(stmt.order_by(order, BulkItem.id).limit(page_size).offset((page - 1) * page_size)).all()
    return rows, total


def existing_application_id(db: Session, item: BulkItem, opening_id: int) -> int | None:
    """Only reveals an application to *this* opening, which the caller is already allowed to see."""
    if not item.existing_candidate_id:
        return None
    return db.scalar(
        select(JobApplication.id).where(JobApplication.candidate_id == item.existing_candidate_id, JobApplication.opening_id == opening_id)
    )


def triage(db: Session, user: User, item: BulkItem, status: ScreeningStatus, note: str | None, request: Request) -> BulkItem:
    item.review_status, item.review_note = status, (note or "").strip() or None
    item.reviewed_by, item.reviewed_at = user.id, utcnow()
    audit_service.log_action(
        db, "bulk_item.triage", actor=user, entity_type="bulk_item", entity_id=item.id, request=request, details={"status": status.value}
    )
    db.commit()
    return item


def retry(db: Session, user: User, batch: BulkBatch, item_id: int | None, request: Request) -> int:
    stmt = update(BulkItem).where(BulkItem.batch_id == batch.id, BulkItem.status == BulkItemStatus.FAILED)
    if item_id is not None:
        stmt = stmt.where(BulkItem.id == item_id)
    n = db.execute(stmt.values(status=BulkItemStatus.QUEUED, attempts=0, error=None)).rowcount or 0
    if n:
        audit_service.log_action(
            db, "bulk_batch.retry", actor=user, entity_type="bulk_batch", entity_id=batch.id, request=request, details={"items": n}
        )
    db.commit()
    return n


def delete_batch(db: Session, user: User, batch: BulkBatch, request: Request) -> None:
    names = db.scalars(select(BulkItem.stored_name).where(BulkItem.batch_id == batch.id)).all()
    audit_service.log_action(
        db, "bulk_batch.delete", actor=user, entity_type="bulk_batch", entity_id=batch.id, request=request,
        details={"name": batch.name, "files": len(names)},
    )
    db.delete(batch)
    db.commit()
    for n in names:  # files are removed only after the rows are gone
        storage_service.delete(n)
