from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.api.dependencies.auth import CurrentUser, DbSession
from app.api.routes.applicants import staff_can_view_candidate
from app.core.errors import AppError
from app.models import CandidateProfile, CandidateResume, Role
from app.services import audit_service, storage_service

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.get("/{resume_id}/file")
def download_resume(resume_id: int, request: Request, user: CurrentUser, db: DbSession, download: bool = False):
    """Authorised download. The storage path is never exposed; access is re-checked on every request."""
    resume = db.get(CandidateResume, resume_id)
    allowed = False
    if resume is not None:
        cp = db.get(CandidateProfile, resume.candidate_id)
        if user.role == Role.APPLICANT:
            allowed = cp is not None and cp.user_id == user.id
        else:
            allowed = staff_can_view_candidate(db, user, resume.candidate_id)
    if resume is None or not allowed:
        raise AppError(404, "not_found", "Resume not found.")
    try:
        path = storage_service.path_for(resume.stored_name)
    except ValueError as exc:
        raise AppError(404, "not_found", "Resume not found.") from exc
    if not path.exists():
        raise AppError(404, "file_missing", "The stored file is missing. Please contact support.")
    audit_service.log_action(db, "resume.downloaded", actor=user, entity_type="candidate_resume", entity_id=resume.id, request=request)
    db.commit()
    inline = resume.content_type == "application/pdf" and not download
    return FileResponse(
        path, media_type=resume.content_type, filename=resume.original_filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "private, no-store"},
    )
