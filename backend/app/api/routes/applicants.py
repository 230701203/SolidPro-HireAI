from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import ApplicantUser, DbSession, ReviewApplications
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import CandidateProfile, JobApplication, User
from app.schemas.common import make_page
from app.schemas.recruitment import ApplicantListItem, ProfileIn, ProfileOut, ResumeOut
from app.services import access, audit_service, profile_service

router = APIRouter(prefix="/applicants", tags=["Applicants"])


# ------------------------------------------------------------------ the applicant's own profile


@router.get("/profile", response_model=ProfileOut)
def my_profile(user: ApplicantUser, db: DbSession):
    cp = profile_service.get_candidate(db, user)
    db.commit()
    return profile_service.build_profile(db, cp)


@router.put("/profile", response_model=ProfileOut)
def update_my_profile(data: ProfileIn, request: Request, user: ApplicantUser, db: DbSession):
    cp = profile_service.get_candidate(db, user)
    profile_service.update_profile(db, cp, data)
    audit_service.log_action(db, "profile.updated", actor=user, entity_type="candidate_profile", entity_id=cp.id, request=request)
    db.commit()
    return profile_service.build_profile(db, cp)


@router.get("/resumes", response_model=list[ResumeOut])
def my_resumes(user: ApplicantUser, db: DbSession):
    return profile_service.build_profile(db, profile_service.get_candidate(db, user)).resumes


@router.post("/resumes", response_model=ResumeOut, status_code=201, dependencies=[Depends(rate_limit("resume_upload", 20, 3600))])
def upload_resume(request: Request, user: ApplicantUser, db: DbSession, file: UploadFile = File(...)):
    """Each upload becomes a new immutable version; earlier versions (and applications using them) are kept."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)  # never read more than the limit + 1 byte into memory
    cp = profile_service.get_candidate(db, user)
    resume = profile_service.add_resume(db, cp, file.filename or "resume", data, user)
    audit_service.log_action(db, "resume.uploaded", actor=user, entity_type="candidate_resume", entity_id=resume.id, details={"version": resume.version, "size": resume.size_bytes}, request=request)
    db.commit()
    return ResumeOut(id=resume.id, version=resume.version, original_filename=resume.original_filename, content_type=resume.content_type, size_bytes=resume.size_bytes, created_at=resume.created_at, is_current=True)


# ------------------------------------------------------------------ recruiters


def _scoped_candidate_ids(db, user: User):
    scope = access.staff_scope(db, user)
    if scope is None:
        return None
    return select(JobApplication.candidate_id).where(JobApplication.opening_id.in_(scope))


@router.get("")
def list_applicants(
    user: ReviewApplications, db: DbSession, search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    """Admins see every applicant; employees only people who applied to their assigned openings."""
    q = select(CandidateProfile, User).join(User, User.id == CandidateProfile.user_id)
    ids = _scoped_candidate_ids(db, user)
    if ids is not None:
        q = q.where(CandidateProfile.id.in_(ids))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(User.full_name.ilike(like), User.email.ilike(like), User.mobile.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(User.created_at.desc(), User.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    counts = dict(db.execute(select(JobApplication.candidate_id, func.count()).where(JobApplication.candidate_id.in_([cp.id for cp, _ in rows])).group_by(JobApplication.candidate_id)).all()) if rows else {}
    items = [
        ApplicantListItem(candidate_id=cp.id, user_id=u.id, full_name=u.full_name, email=u.email, mobile=u.mobile, city=cp.city,
                          highest_qualification=cp.highest_qualification, applications_count=counts.get(cp.id, 0), created_at=u.created_at)
        for cp, u in rows
    ]
    return make_page(items, total, page, page_size)


def staff_can_view_candidate(db, user: User, candidate_id: int) -> bool:
    if user.role.value == "admin":
        return True
    if not access.has_permission(db, user, "review_applications"):
        return False
    scope = access.staff_scope(db, user) or []
    return db.scalar(select(JobApplication.id).where(JobApplication.candidate_id == candidate_id, JobApplication.opening_id.in_(scope)).limit(1)) is not None


@router.get("/{candidate_id}", response_model=ProfileOut)
def applicant_detail(candidate_id: int, request: Request, user: ReviewApplications, db: DbSession):
    cp = db.get(CandidateProfile, candidate_id)
    if cp is None or not staff_can_view_candidate(db, user, candidate_id):
        raise AppError(404, "not_found", "Applicant not found.")  # same answer for "missing" and "not yours"
    audit_service.log_action(db, "applicant.viewed", actor=user, entity_type="candidate_profile", entity_id=cp.id, request=request)
    db.commit()
    return profile_service.build_profile(db, cp)
