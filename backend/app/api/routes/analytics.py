"""Recruitment analytics (staff with view_analytics; data limited to openings the viewer may access)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.services import analytics_service as svc
from app.services import audit_service, export_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _filters(date_from: date | None = None, date_to: date | None = None, opening_id: int | None = None,
             category_id: int | None = None, employee_id: int | None = None) -> svc.Filters:
    return svc.Filters(date_from, date_to, opening_id, category_id, employee_id)


@router.get("/recruitment")
def recruitment(user: CurrentUser, db: DbSession, f: svc.Filters = Depends(_filters)):
    svc.require(db, user)
    return svc.recruitment(db, user, f)


@router.get("/compare")
def compare(user: CurrentUser, db: DbSession, application_ids: list[int] = Query(...)):
    return svc.compare(db, user, application_ids)


@router.get("/export", dependencies=[Depends(rate_limit("analytics_export", 30, 3600))])
def export(
    request: Request, user: CurrentUser, db: DbSession, f: svc.Filters = Depends(_filters),
    report: Literal["openings", "categories", "monthly", "funnel"] = "openings", format: Literal["csv", "xlsx"] = "csv",
):
    svc.require(db, user)
    data = svc.recruitment(db, user, f)
    headers, rows = svc.export_rows(data, report)
    audit_service.log_action(db, "analytics.export", actor=user, entity_type="analytics", request=request, details={"report": report, "format": format, "rows": len(rows)})
    db.commit()
    return export_service.respond(format, f"recruitment-{report}", headers, rows, report.title())
