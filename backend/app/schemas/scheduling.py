from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.scheduling import AttemptStatus, RescheduleStatus, ScheduleStatus


def _aware(v: datetime | None) -> datetime | None:
    if v is not None and (v.tzinfo is None or v.utcoffset() is None):
        raise ValueError("Date and time must include a timezone (for example 2026-12-01T10:00:00+05:30)")
    return v


class ScheduleCreate(BaseModel):
    application_id: int
    window_start: datetime
    window_end: datetime
    duration_minutes: int | None = Field(default=None, ge=5, le=240)  # defaults to the assessment's duration
    instructions: str | None = Field(default=None, max_length=3000)
    link_expires_at: datetime | None = None  # defaults to window_end

    _tz = field_validator("window_start", "window_end", "link_expires_at")(_aware)

    @model_validator(mode="after")
    def _order(self):
        if self.window_end <= self.window_start:
            raise ValueError("The window must end after it starts")
        return self


class ScheduleUpdate(BaseModel):
    window_start: datetime | None = None
    window_end: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    instructions: str | None = Field(default=None, max_length=3000)

    _tz = field_validator("window_start", "window_end")(_aware)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RescheduleIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    preferred_start: datetime | None = None

    _tz = field_validator("preferred_start")(_aware)


class RescheduleDecision(BaseModel):
    action: Literal["approve", "reject", "suggest"]
    comment: str | None = Field(default=None, max_length=1000)
    new_window_start: datetime | None = None
    new_window_end: datetime | None = None

    _tz = field_validator("new_window_start", "new_window_end")(_aware)

    @model_validator(mode="after")
    def _need_window(self):
        if self.action in ("approve", "suggest"):
            if not (self.new_window_start and self.new_window_end):
                raise ValueError("Provide the new window")
            if self.new_window_end <= self.new_window_start:
                raise ValueError("The window must end after it starts")
        if self.action == "reject" and not (self.comment and self.comment.strip()):
            raise ValueError("Give a reason when declining a reschedule request")
        return self


class AlternativeResponse(BaseModel):
    accept: bool


class StartRequest(BaseModel):
    consent: bool


class RescheduleOut(BaseModel):
    id: int
    reason: str
    preferred_start: datetime | None
    status: RescheduleStatus
    comment: str | None
    new_window_start: datetime | None
    new_window_end: datetime | None
    created_at: datetime
    decided_at: datetime | None


class EventOut(BaseModel):
    id: int
    kind: str
    client_reported: bool
    details: dict | None
    created_at: datetime


class AttemptSummary(BaseModel):
    id: int
    status: AttemptStatus
    started_at: datetime
    deadline_at: datetime
    submitted_at: datetime | None
    submit_reason: str | None
    answered: int
    total_questions: int
    recordings: int


class ScheduleListItem(BaseModel):
    id: int
    application_id: int
    candidate_name: str
    opening_title: str
    assessment_title: str
    status: ScheduleStatus
    window_start: datetime
    window_end: datetime
    duration_minutes: int
    pending_reschedule: bool
    attempt_status: AttemptStatus | None


class ScheduleDetail(ScheduleListItem):
    assessment_id: int
    version: int
    is_mock: bool
    instructions: str | None
    link_expires_at: datetime
    accepted_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    candidate_email: str
    reschedules: list[RescheduleOut]
    events: list[EventOut]
    attempt: AttemptSummary | None
    can_edit: bool
    can_manage: bool
    evaluation_id: int | None = None
    invite_link: str | None = None  # present only in the response that created / resent the invitation


class InvitationSection(BaseModel):
    kind: str
    title: str
    questions: int


class InvitationOut(BaseModel):
    id: int
    application_id: int
    opening_title: str
    assessment_title: str
    status: ScheduleStatus
    window_start: datetime
    window_end: datetime
    duration_minutes: int
    instructions: str | None
    link_expires_at: datetime
    sections: list[InvitationSection]
    has_repeat_sentence: bool
    rs_max_replays: int | None
    rs_max_attempts: int | None
    rs_record_seconds: int | None
    can_accept: bool
    can_start: bool
    start_blocked_reason: str | None
    can_request_reschedule: bool
    attempt_id: int | None
    reschedules: list[RescheduleOut]
    server_now: datetime


# ---- test taking -------------------------------------------------------------------------------

class TakeOption(BaseModel):
    id: int  # index in the original option list; the client never learns which one is correct
    text: str


class TakeQuestion(BaseModel):
    id: int
    section: str
    position: int
    text: str | None  # None for Repeat the Sentence: the sentence is only revealed by the play endpoint
    options: list[TakeOption] | None
    marks: int
    selected: int | None = None
    marked: bool = False
    plays_used: int = 0
    plays_allowed: int | None = None
    recordings_used: int = 0
    recordings_allowed: int | None = None


class TakeSection(BaseModel):
    kind: str
    title: str
    questions: list[TakeQuestion]


class AttemptOut(BaseModel):
    id: int
    status: AttemptStatus
    assessment_title: str
    started_at: datetime
    deadline_at: datetime
    server_now: datetime
    submitted_at: datetime | None
    session_id: str | None  # given back only when the attempt was just opened / resumed
    rs_record_seconds: int | None
    sections: list[TakeSection]


class AnswerItem(BaseModel):
    question_id: int
    selected_index: int | None = None
    marked_for_review: bool = False
    seq: int = Field(ge=0)


class AnswersIn(BaseModel):
    answers: list[AnswerItem] = Field(min_length=1, max_length=200)


class AnswersSaved(BaseModel):
    saved: int
    server_now: datetime
    deadline_at: datetime


class PlayOut(BaseModel):
    sentence: str
    plays_used: int
    plays_allowed: int
    mock_audio_note: str


class ClientEvent(BaseModel):
    kind: Literal["tab_hidden", "tab_visible", "copy", "paste", "offline", "online", "mic_denied", "recording_failed", "fullscreen_exit"]
    at: datetime | None = None
    detail: str | None = Field(default=None, max_length=200)


class EventsIn(BaseModel):
    events: list[ClientEvent] = Field(min_length=1, max_length=50)


class RecordingOut(BaseModel):
    id: int
    question_id: int
    attempt_no: int
    size_bytes: int
    duration_ms: int | None
    mime: str
    created_at: datetime


class SubmitOut(BaseModel):
    status: AttemptStatus
    submitted_at: datetime | None
    submit_reason: str | None
    answered: int
    total_questions: int
