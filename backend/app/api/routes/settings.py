from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.auth import AdminUser, DbSession
from app.core.errors import AppError
from app.models import CompanyEmailDomain, EmailLog, EmailStatus
from app.schemas.admin import EmailDomainCreate, EmailDomainOut, EmailDomainUpdate, EmailLogOut
from app.schemas.common import make_page
from app.services import audit_service, email_service

router = APIRouter(prefix="/settings", tags=["System settings"])


@router.get("/email-domains", response_model=list[EmailDomainOut])
def list_domains(_: AdminUser, db: DbSession):
    return db.scalars(select(CompanyEmailDomain).order_by(CompanyEmailDomain.domain)).all()


@router.post("/email-domains", response_model=EmailDomainOut, status_code=201)
def add_domain(data: EmailDomainCreate, request: Request, admin: AdminUser, db: DbSession):
    domain = CompanyEmailDomain(domain=data.domain, created_by=admin.id)
    db.add(domain)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "domain_exists", "This domain is already in the list.") from exc
    audit_service.log_action(db, "settings.domain_added", actor=admin, entity_type="company_email_domain", entity_id=domain.id, details={"domain": data.domain}, request=request)
    db.commit()
    return domain


@router.patch("/email-domains/{domain_id}", response_model=EmailDomainOut)
def update_domain(domain_id: int, data: EmailDomainUpdate, request: Request, admin: AdminUser, db: DbSession):
    """Deactivating a domain only affects NEW registrations; existing employees keep their accounts."""
    domain = db.get(CompanyEmailDomain, domain_id)
    if domain is None:
        raise AppError(404, "not_found", "Domain not found.")
    domain.is_active = data.is_active
    audit_service.log_action(
        db, "settings.domain_activated" if data.is_active else "settings.domain_deactivated",
        actor=admin, entity_type="company_email_domain", entity_id=domain.id, details={"domain": domain.domain}, request=request,
    )
    db.commit()
    return domain


@router.get("/email-logs")
def list_email_logs(
    _: AdminUser,
    db: DbSession,
    status: EmailStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(EmailLog)
    if status:
        stmt = stmt.where(EmailLog.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(EmailLog.created_at.desc(), EmailLog.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return make_page([EmailLogOut.model_validate(r) for r in rows], total, page, page_size)


@router.post("/email-logs/{log_id}/retry", response_model=EmailLogOut)
def retry_email(log_id: int, background: BackgroundTasks, request: Request, admin: AdminUser, db: DbSession):
    log = db.get(EmailLog, log_id)
    if log is None:
        raise AppError(404, "not_found", "Email log not found.")
    if log.status != EmailStatus.FAILED:
        raise AppError(409, "invalid_state", "Only failed emails can be retried.")
    log.status = EmailStatus.QUEUED
    audit_service.log_action(db, "email.retry", actor=admin, entity_type="email_log", entity_id=log.id, request=request)
    db.commit()
    background.add_task(email_service.deliver_email, log.id)
    return log
