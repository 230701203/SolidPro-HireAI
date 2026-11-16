from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.evaluation import InterviewMode, InterviewStatus, InterviewType, Recommendation


def _aware(v: datetime | None) -> datetime | None:
    if v is not None and (v.tzinfo is None or v.utcoffset() is None):
        raise ValueError("Date and time must include a timezone (for example 2026-12-01T10:00:00+05:30)")
    return v


def _link(v: str | None) -> str | None:
    if v is not None and v.strip() and not v.strip().lower().startswith(("https://", "http://")):
        raise ValueError("The meeting link must start with https://")
    return v.strip() if v and v.strip() else None


class InterviewCreate(BaseModel):
    application_id: int
    interviewer_id: int | None = None
    interview_type: InterviewType = InterviewType.TECHNICAL
    mode: InterviewMode = InterviewMode.ONLINE
    scheduled_start: datetime | None = None  # without a time the interview stays "pending"
    duration_minutes: int = Field(default=45, ge=10, le=480)
    meeting_link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, max_length=3000)

    _tz = field_validator("scheduled_start")(_aware)
    _lk = field_validator("meeting_link")(_link)


class InterviewUpdate(BaseModel):
    interviewer_id: int | None = None
    interview_type: InterviewType | None = None
    mode: InterviewMode | None = None
    scheduled_start: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=10, le=480)
    meeting_link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, max_length=3000)

    _tz = field_validator("scheduled_start")(_aware)
    _lk = field_validator("meeting_link")(_link)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class FeedbackIn(BaseModel):
    technical_feedback: str | None = Field(default=None, max_length=4000)
    communication_feedback: str | None = Field(default=None, max_length=4000)
    strengths: str | None = Field(default=None, max_length=4000)
    improvements: str | None = Field(default=None, max_length=4000)
    recommendation: Recommendation


class FeedbackOut(FeedbackIn):
    submitted_by: str | None
    updated_at: datetime


class InterviewerRef(BaseModel):
    id: int
    full_name: str


class InterviewOut(BaseModel):
    id: int
    application_id: int
    candidate_name: str
    opening_title: str
    interviewer: InterviewerRef | None
    interview_type: InterviewType
    mode: InterviewMode
    status: InterviewStatus
    scheduled_start: datetime | None
    duration_minutes: int
    meeting_link: str | None
    location: str | None
    instructions: str | None
    cancel_reason: str | None
    feedback: FeedbackOut | None
    can_manage: bool
    can_give_feedback: bool


class MyInterview(BaseModel):
    id: int
    opening_title: str
    interview_type: InterviewType
    mode: InterviewMode
    status: InterviewStatus
    scheduled_start: datetime | None
    duration_minutes: int
    meeting_link: str | None
    location: str | None
    instructions: str | None
