from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateResume,
    CandidateSkill,
    SkillKind,
    User,
)
from app.schemas.recruitment import ProfileIn, ProfileOut
from app.services import document_service, storage_service


def get_candidate(db: Session, user: User) -> CandidateProfile:
    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if cp is None:  # defensive: every applicant gets one at registration
        cp = CandidateProfile(user_id=user.id)
        db.add(cp)
        db.flush()
    return cp


def current_resume(db: Session, candidate_id: int) -> CandidateResume | None:
    return db.scalar(
        select(CandidateResume).where(CandidateResume.candidate_id == candidate_id).order_by(CandidateResume.version.desc()).limit(1)
    )


def build_profile(db: Session, cp: CandidateProfile) -> ProfileOut:
    user = db.get(User, cp.user_id)
    assert user is not None
    edu = db.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == cp.id).order_by(CandidateEducation.graduation_year.desc().nulls_last(), CandidateEducation.id)).all()
    exp = db.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == cp.id).order_by(CandidateExperience.start_date.desc().nulls_last(), CandidateExperience.id)).all()
    skills = db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cp.id).order_by(CandidateSkill.kind, CandidateSkill.name)).all()
    resumes = db.scalars(select(CandidateResume).where(CandidateResume.candidate_id == cp.id).order_by(CandidateResume.version.desc())).all()

    checks = {
        "Mobile number": bool(user.mobile),
        "City and country": bool(cp.city and cp.country),
        "Highest qualification": bool(cp.highest_qualification),
        "At least one education entry": bool(edu),
        "At least one technical skill": any(s.kind == SkillKind.TECHNICAL for s in skills),
        "Total experience (0 for freshers)": cp.total_experience_years is not None,
        "LinkedIn, GitHub or portfolio link": bool(cp.linkedin_url or cp.github_url or cp.portfolio_url),
        "Work, internship or project entry": bool(exp),
        "Uploaded resume": bool(resumes),
    }
    missing = [k for k, ok in checks.items() if not ok]
    completion = round(100 * (len(checks) - len(missing)) / len(checks))
    return ProfileOut.model_validate(
        {
            "candidate_id": cp.id, "user_id": user.id, "full_name": user.full_name, "email": user.email, "mobile": user.mobile,
            "date_of_birth": cp.date_of_birth, "address": cp.address, "city": cp.city, "state": cp.state, "country": cp.country,
            "linkedin_url": cp.linkedin_url, "portfolio_url": cp.portfolio_url, "github_url": cp.github_url,
            "highest_qualification": cp.highest_qualification, "total_experience_years": cp.total_experience_years,
            "education": [{c: getattr(e, c) for c in ("id", "degree", "institution", "department", "graduation_year", "grade")} for e in edu],
            "experience": [{c: getattr(e, c) for c in ("id", "kind", "organization", "title", "start_date", "end_date", "description")} for e in exp],
            "skills": [{"id": s.id, "name": s.name, "kind": s.kind} for s in skills],
            "resumes": [
                {"id": r.id, "version": r.version, "original_filename": r.original_filename, "content_type": r.content_type,
                 "size_bytes": r.size_bytes, "created_at": r.created_at, "is_current": i == 0}
                for i, r in enumerate(resumes)
            ],
            "completion": completion, "missing": missing,
        }
    )


def update_profile(db: Session, cp: CandidateProfile, data: ProfileIn) -> None:
    for field in ("date_of_birth", "address", "city", "state", "country", "linkedin_url", "portfolio_url", "github_url", "highest_qualification", "total_experience_years"):
        value = getattr(data, field)
        if isinstance(value, str):
            value = value.strip() or None
        setattr(cp, field, value)

    # The profile form submits whole lists; replace them atomically.
    db.execute(delete(CandidateEducation).where(CandidateEducation.candidate_id == cp.id))
    db.execute(delete(CandidateExperience).where(CandidateExperience.candidate_id == cp.id))
    db.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == cp.id))
    for e in data.education:
        db.add(CandidateEducation(candidate_id=cp.id, **e.model_dump()))
    for x in data.experience:
        db.add(CandidateExperience(candidate_id=cp.id, **x.model_dump()))
    seen: set[tuple[str, str]] = set()
    for s in data.skills:
        key = (s.kind.value, s.name.strip().lower())
        if key in seen or not s.name.strip():
            continue
        seen.add(key)
        db.add(CandidateSkill(candidate_id=cp.id, kind=s.kind, name=s.name.strip()))
    db.flush()


def add_resume(db: Session, cp: CandidateProfile, filename: str, data: bytes, uploaded_by: User) -> CandidateResume:
    import hashlib

    parsed = document_service.validate_and_extract(filename, data)
    stored = storage_service.save_bytes(data)
    try:
        next_version = (db.scalar(select(func.max(CandidateResume.version)).where(CandidateResume.candidate_id == cp.id)) or 0) + 1
        resume = CandidateResume(
            candidate_id=cp.id, version=next_version, original_filename=document_service.safe_filename(filename),
            stored_name=stored, content_type=parsed.content_type, size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), extracted_text=parsed.text, uploaded_by=uploaded_by.id,
        )
        db.add(resume)
        db.flush()
    except Exception:
        storage_service.delete(stored)
        raise
    return resume


def require_ready_to_apply(db: Session, cp: CandidateProfile, user: User) -> None:
    has_edu = db.scalar(select(func.count()).select_from(CandidateEducation).where(CandidateEducation.candidate_id == cp.id))
    problems = []
    if not user.mobile:
        problems.append("mobile number")
    if not has_edu:
        problems.append("at least one education entry")
    if current_resume(db, cp.id) is None:
        problems.append("a resume")
    if problems:
        raise AppError(422, "profile_incomplete", "Complete your profile before applying: add " + ", ".join(problems) + ".")
