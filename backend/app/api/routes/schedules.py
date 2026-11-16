"""Staff scheduling endpoints (requires `schedule_tests` and access to the opening)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.schemas.common import Page, make_page
from app.schemas.scheduling import (
    CancelRequest, RecordingOut, RescheduleDecision, ScheduleCreate, ScheduleDetail, ScheduleListItem, ScheduleUpdate,
)
from app.services import attempt_service as attempts
from app.services import scheduling_service as svc

router = APIRouter(tags=["Scheduling"])


@router.get("/schedules", response_model=Page[ScheduleListItem])
def list_schedules(user: CurrentUser, db: DbSession, status: str | None = None, application_id: int | None = None, search: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=100)):
    items, total = svc.list_schedules(db, user, status=status, application_id=application_id, search=search, page=page, page_size=page_size)
    return make_page(items, total, page, page_size)


@router.post("/schedules", response_model=ScheduleDetail, status_code=201, dependencies=[Depends(rate_limit("schedule_create", 60, 3600))])
def create(data: ScheduleCreate, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.create_schedule(db, user, data, request, background)


@router.get("/schedules/{schedule_id}", response_model=ScheduleDetail)
def get_one(schedule_id: int, user: CurrentUser, db: DbSession):
    return svc.detail(db, user, svc.staff_get(db, user, schedule_id))


@router.patch("/schedules/{schedule_id}", response_model=ScheduleDetail)
def update(schedule_id: int, data: ScheduleUpdate, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.update_schedule(db, user, svc.staff_get(db, user, schedule_id), data, request, background)


@router.post("/schedules/{schedule_id}/cancel", response_model=ScheduleDetail)
def cancel(schedule_id: int, data: CancelRequest, request: Request, user: CurrentUser, db: DbSession):
    return svc.cancel_schedule(db, user, svc.staff_get(db, user, schedule_id), data.reason, request)


@router.post("/schedules/{schedule_id}/resend", response_model=ScheduleDetail, dependencies=[Depends(rate_limit("schedule_resend", 30, 3600))])
def resend(schedule_id: int, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.resend_invitation(db, user, svc.staff_get(db, user, schedule_id), request, background)


@router.post("/schedules/{schedule_id}/reschedule-requests/{request_id}", response_model=ScheduleDetail)
def decide(schedule_id: int, request_id: int, data: RescheduleDecision, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession):
    return svc.decide_reschedule(db, user, svc.staff_get(db, user, schedule_id), request_id, data, request, background)


@router.get("/schedules/{schedule_id}/recordings", response_model=list[RecordingOut])
def recordings(schedule_id: int, user: CurrentUser, db: DbSession):
    return attempts.list_recordings(db, user, schedule_id)


@router.get("/recordings/{recording_id}/file")
def recording_file(recording_id: int, request: Request, user: CurrentUser, db: DbSession):
    """Authorised playback. Access is re-checked and audited on every request; the storage path is never exposed."""
    path, mime = attempts.recording_file(db, user, recording_id, request)
    return FileResponse(path, media_type=mime, content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "private, no-store"})
