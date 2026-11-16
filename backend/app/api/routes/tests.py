"""Applicant-facing invitations and the online test runner. Applicants only ever see their own data."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Request, UploadFile

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.schemas.scheduling import (
    AlternativeResponse, AnswersIn, AnswersSaved, AttemptOut, EventsIn, InvitationOut, PlayOut, RecordingOut, RescheduleIn, StartRequest, SubmitOut,
)
from app.services import attempt_service as attempts
from app.services import evaluation_service
from app.services import scheduling_service as svc

router = APIRouter(tags=["Online tests"])
SessionHeader = Header(default=None, alias="X-Attempt-Session")


@router.get("/test-invitations", response_model=list[InvitationOut])
def my_invitations(user: CurrentUser, db: DbSession):
    return svc.my_invitations(db, user)


@router.get("/test-invitations/by-token/{token}", response_model=InvitationOut, dependencies=[Depends(rate_limit("invite_token", 30, 600))])
def by_token(token: str, user: CurrentUser, db: DbSession):
    return svc.invitation_out(db, svc.by_token(db, user, token))


@router.get("/test-invitations/{schedule_id}", response_model=InvitationOut)
def get_one(schedule_id: int, user: CurrentUser, db: DbSession):
    out = svc.invitation_out(db, svc.my_invitation(db, user, schedule_id))
    db.commit()
    return out


@router.post("/test-invitations/{schedule_id}/accept", response_model=InvitationOut)
def accept(schedule_id: int, request: Request, user: CurrentUser, db: DbSession):
    return svc.invitation_out(db, svc.accept(db, user, svc.my_invitation(db, user, schedule_id), request))


@router.post("/test-invitations/{schedule_id}/reschedule", response_model=InvitationOut, status_code=201)
def reschedule(schedule_id: int, data: RescheduleIn, request: Request, user: CurrentUser, db: DbSession):
    return svc.invitation_out(db, svc.request_reschedule(db, user, svc.my_invitation(db, user, schedule_id), data, request))


@router.post("/test-invitations/{schedule_id}/reschedule/{request_id}/respond", response_model=InvitationOut)
def respond(schedule_id: int, request_id: int, data: AlternativeResponse, request: Request, user: CurrentUser, db: DbSession):
    return svc.invitation_out(db, svc.respond_alternative(db, user, svc.my_invitation(db, user, schedule_id), request_id, data.accept, request))


@router.post("/test-invitations/{schedule_id}/start", response_model=AttemptOut, dependencies=[Depends(rate_limit("attempt_start", 20, 600))])
def start(schedule_id: int, data: StartRequest, request: Request, user: CurrentUser, db: DbSession):
    return attempts.start(db, user, svc.my_invitation(db, user, schedule_id), data.consent, request)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(attempt_id: int, user: CurrentUser, db: DbSession):
    return attempts.get_attempt(db, user, attempt_id)


@router.put("/attempts/{attempt_id}/answers", response_model=AnswersSaved)
def save_answers(attempt_id: int, data: AnswersIn, user: CurrentUser, db: DbSession, session: str | None = SessionHeader):
    return attempts.save_answers(db, user, attempt_id, data, session)


@router.post("/attempts/{attempt_id}/questions/{question_id}/play", response_model=PlayOut)
def play(attempt_id: int, question_id: int, user: CurrentUser, db: DbSession, session: str | None = SessionHeader):
    return attempts.play(db, user, attempt_id, question_id, session)


@router.post("/attempts/{attempt_id}/questions/{question_id}/recording", response_model=RecordingOut, status_code=201,
             dependencies=[Depends(rate_limit("recording_upload", 60, 600))])
async def upload_recording(attempt_id: int, question_id: int, user: CurrentUser, db: DbSession, file: UploadFile = File(...),
                           duration_ms: int | None = Form(default=None), session: str | None = SessionHeader):
    return await attempts.upload_recording(db, user, attempt_id, question_id, file, duration_ms, session)


@router.post("/attempts/{attempt_id}/events")
def events(attempt_id: int, data: EventsIn, user: CurrentUser, db: DbSession, session: str | None = SessionHeader):
    return {"recorded": attempts.record_events(db, user, attempt_id, data, session)}


@router.post("/attempts/{attempt_id}/submit", response_model=SubmitOut)
def submit(attempt_id: int, request: Request, background: BackgroundTasks, user: CurrentUser, db: DbSession, session: str | None = SessionHeader):
    out = attempts.submit(db, user, attempt_id, request, session)
    background.add_task(evaluation_service.process_speech_for_attempt, attempt_id)  # transcribe after the response is sent
    return out
