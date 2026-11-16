"""Runs AI resume analysis and manages reviewer overrides.

Rules enforced here:
* Advisory only: nothing in this module changes an application's status.
* The provider only sees job data plus profile facts. Name, contact details, date of birth and address are not sent.
* Every run is stored (success or failure) with provider, model and prompt version.
* A reviewer override sits beside the AI score; the AI score is never rewritten.
"""

import re

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.factory import get_provider, provider_status
from app.ai.schemas import PROMPT_VERSION, AIProviderError, AnalysisInput
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AnalysisStatus,
    CandidateEducation,
    CandidateProfile,
    CandidateSkill,
    JobApplication,
    ResumeAnalysisReport,
    User,
)
from app.models.base import utcnow
from app.schemas.analysis import AIStatusOut, AnalysisOverview, AnalysisReportOut
from app.services import access, audit_service

INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any |the )?(previous|above|prior) (instructions|prompts?)|disregard (the )?(above|previous)"
    r"|system prompt|you are now|give (this|the) (candidate|applicant) (a )?(score|rating)|score of 100|rate (this|me) 100)",
    re.IGNORECASE,
)
INJECTION_NOTE = "The resume contains text that looks like instructions to an AI system. It was ignored. Review the resume yourself."


def can_view(db: Session, user: User) -> bool:
    return access.has_permission(db, user, "analyze_resumes") or access.has_permission(db, user, "review_applications")


def require_view(db: Session, user: User, app: JobApplication) -> None:
    if not can_view(db, user):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")
    access.require_opening_access(db, user, app.opening_id)


def require_run(db: Session, user: User, app: JobApplication) -> None:
    access.require_perm(db, user, "analyze_resumes")
    access.require_opening_access(db, user, app.opening_id)


def build_input(db: Session, app: JobApplication) -> AnalysisInput:
    text = (app.resume.extracted_text or "").strip()
    if not text:
        raise AppError(422, "no_resume_text", "This resume has no readable text to analyse.")
    cp = db.get(CandidateProfile, app.candidate_id)
    edu = db.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == cp.id)).all()
    skills = db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cp.id)).all()
    o = app.opening
    return AnalysisInput(
        job_title=o.title, job_description=o.description, required_skills=list(o.required_skills or []),
        preferred_skills=list(o.preferred_skills or []), required_qualifications=o.required_qualifications,
        required_experience=o.required_experience,
        candidate_experience_years=float(cp.total_experience_years) if cp.total_experience_years is not None else None,
        candidate_education=[{"degree": e.degree, "department": e.department, "graduation_year": e.graduation_year} for e in edu],
        candidate_skills=[s.name for s in skills],
        resume_text=text[: get_settings().ai_max_resume_chars],
    )


def to_out(db: Session, r: ResumeAnalysisReport) -> AnalysisReportOut:
    from app.models import CandidateResume
    from app.schemas.analysis import ResumeAnalysisResult

    by = db.get(User, r.requested_by) if r.requested_by else None
    ov = db.get(User, r.overridden_by) if r.overridden_by else None
    resume = db.get(CandidateResume, r.resume_id)
    return AnalysisReportOut(
        id=r.id, application_id=r.application_id, resume_id=r.resume_id, resume_version=resume.version if resume else 0,
        status=r.status, provider=r.provider, model=r.model, prompt_version=r.prompt_version, is_mock=r.is_mock,
        ai_score=r.ai_score, effective_score=r.override_score if r.override_score is not None else r.ai_score,
        report=ResumeAnalysisResult.model_validate(r.report) if r.report else None, error=r.error,
        requested_by_name=by.full_name if by else None, created_at=r.created_at,
        override_score=r.override_score, override_note=r.override_note,
        overridden_by_name=ov.full_name if ov else None, overridden_at=r.overridden_at,
    )


def overview(db: Session, user: User, app: JobApplication) -> AnalysisOverview:
    rows = db.scalars(
        select(ResumeAnalysisReport).where(ResumeAnalysisReport.application_id == app.id).order_by(ResumeAnalysisReport.id.desc())
    ).all()
    outs = [to_out(db, r) for r in rows]
    return AnalysisOverview(
        ai=AIStatusOut(**provider_status()), can_run=access.has_permission(db, user, "analyze_resumes"),
        latest=outs[0] if outs else None, history=outs[1:],
    )


def run(db: Session, user: User, app: JobApplication, request: Request) -> ResumeAnalysisReport:
    try:
        provider = get_provider()
    except AIProviderError as e:
        raise AppError(503, "ai_unavailable", str(e)) from e
    data = build_input(db, app)
    suspicious = bool(INJECTION_PATTERNS.search(data.resume_text))
    row = ResumeAnalysisReport(
        application_id=app.id, resume_id=app.resume_id, provider=provider.name, model=provider.model,
        prompt_version=PROMPT_VERSION, is_mock=provider.is_mock, requested_by=user.id, status=AnalysisStatus.FAILED,
    )
    try:
        result = provider.analyze_resume(data)
        if suspicious:
            result.clarifications_to_verify.insert(0, INJECTION_NOTE)
        row.status = AnalysisStatus.COMPLETED
        row.ai_score = result.match_score
        row.report = result.model_dump()
    except AIProviderError as e:
        row.error = str(e)
    db.add(row)
    db.flush()
    audit_service.log_action(
        db, "resume_analysis.run", actor=user, entity_type="job_application", entity_id=app.id, request=request,
        details={"report_id": row.id, "provider": provider.name, "mock": provider.is_mock, "status": row.status.value, "injection_suspected": suspicious},
    )
    db.commit()
    return row


def _get_report(db: Session, report_id: int) -> ResumeAnalysisReport:
    r = db.get(ResumeAnalysisReport, report_id)
    if r is None:
        raise AppError(404, "not_found", "Analysis report not found.")
    return r


def override(db: Session, user: User, report_id: int, score: int, note: str, request: Request) -> ResumeAnalysisReport:
    r = _get_report(db, report_id)
    app = db.get(JobApplication, r.application_id)
    require_run(db, user, app)
    if r.status != AnalysisStatus.COMPLETED:
        raise AppError(409, "report_failed", "A failed analysis has no score to override.")
    previous = r.override_score
    r.override_score, r.override_note, r.overridden_by, r.overridden_at = score, note.strip(), user.id, utcnow()
    audit_service.log_action(
        db, "resume_analysis.overridden", actor=user, entity_type="job_application", entity_id=app.id, request=request,
        details={"report_id": r.id, "ai_score": r.ai_score, "previous_override": previous, "new_score": score},
    )
    db.commit()
    return r


def clear_override(db: Session, user: User, report_id: int, request: Request) -> ResumeAnalysisReport:
    r = _get_report(db, report_id)
    app = db.get(JobApplication, r.application_id)
    require_run(db, user, app)
    r.override_score = r.override_note = r.overridden_by = r.overridden_at = None
    audit_service.log_action(db, "resume_analysis.override_cleared", actor=user, entity_type="job_application", entity_id=app.id, request=request, details={"report_id": r.id})
    db.commit()
    return r


def report_application(db: Session, report_id: int) -> JobApplication:
    return db.get(JobApplication, _get_report(db, report_id).application_id)
