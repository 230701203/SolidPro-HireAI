"""AI resume analysis (staff only; advisory; applicants never receive any of this)."""

from fastapi import APIRouter, Depends, Request

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import Role
from app.schemas.analysis import AnalysisOverview, AnalysisReportOut, OverrideRequest
from app.services import analysis_service as svc
from app.services.application_service import get_application

router = APIRouter(tags=["AI resume analysis"])


def _staff(user) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")


@router.get("/applications/{application_id}/analysis", response_model=AnalysisOverview)
def get_analysis(application_id: int, user: CurrentUser, db: DbSession):
    _staff(user)
    app = get_application(db, application_id)
    svc.require_view(db, user, app)
    return svc.overview(db, user, app)


@router.post(
    "/applications/{application_id}/analysis", response_model=AnalysisReportOut, status_code=201,
    dependencies=[Depends(rate_limit("ai_analysis", 30, 3600))],
)
def run_analysis(application_id: int, request: Request, user: CurrentUser, db: DbSession):
    _staff(user)
    app = get_application(db, application_id)
    svc.require_run(db, user, app)
    return svc.to_out(db, svc.run(db, user, app, request))


@router.put("/analysis/{report_id}/override", response_model=AnalysisReportOut)
def override(report_id: int, data: OverrideRequest, request: Request, user: CurrentUser, db: DbSession):
    _staff(user)
    return svc.to_out(db, svc.override(db, user, report_id, data.score, data.note, request))


@router.delete("/analysis/{report_id}/override", response_model=AnalysisReportOut)
def clear_override(report_id: int, request: Request, user: CurrentUser, db: DbSession):
    _staff(user)
    return svc.to_out(db, svc.clear_override(db, user, report_id, request))
