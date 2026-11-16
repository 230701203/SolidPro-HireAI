"""Applicant-facing job board. Only published, still-open openings are visible."""

from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import ApplicantUser, DbSession
from app.core.errors import AppError
from app.models import (
    CandidateProfile,
    JobApplication,
    JobCategory,
    JobOpening,
    OpeningStatus,
)
from app.schemas.common import make_page
from app.schemas.recruitment import PublicJobOut

router = APIRouter(prefix="/jobs", tags=["Job board (applicants)"])


def _open_filter():
    return (JobOpening.status == OpeningStatus.PUBLISHED, or_(JobOpening.deadline.is_(None), JobOpening.deadline >= date.today()))


def _public(o: JobOpening, applied: dict[int, int]) -> PublicJobOut:
    data = {k: getattr(o, k) for k in PublicJobOut.model_fields if hasattr(o, k) and k not in ("applied", "application_id")}
    return PublicJobOut(**data, category_name=o.category.name, is_internship=o.category.is_internship, applied=o.id in applied, application_id=applied.get(o.id))


def _applied_map(db, user) -> dict[int, int]:
    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if cp is None:
        return {}
    return dict(db.execute(select(JobApplication.opening_id, JobApplication.id).where(JobApplication.candidate_id == cp.id)).all())


@router.get("")
def browse(
    user: ApplicantUser, db: DbSession, category_id: int | None = None, search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=12, ge=1, le=50),
):
    q = select(JobOpening).where(*_open_filter())
    if category_id:
        q = q.where(JobOpening.category_id == category_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.join(JobCategory, JobCategory.id == JobOpening.category_id).where(or_(JobOpening.title.ilike(like), JobOpening.description.ilike(like), JobCategory.name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(JobOpening.published_at.desc().nulls_last(), JobOpening.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    applied = _applied_map(db, user)
    return make_page([_public(o, applied) for o in rows], total, page, page_size)


@router.get("/{job_id}", response_model=PublicJobOut)
def job_detail(job_id: int, user: ApplicantUser, db: DbSession):
    applied = _applied_map(db, user)
    o = db.scalar(select(JobOpening).where(JobOpening.id == job_id, *_open_filter()))
    if o is None and job_id in applied:
        # Applicants can still see openings they applied to after those close.
        o = db.get(JobOpening, job_id)
    if o is None:
        raise AppError(404, "not_found", "This opening is not available.")
    return _public(o, applied)
