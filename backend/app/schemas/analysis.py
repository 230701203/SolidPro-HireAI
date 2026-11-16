from datetime import datetime

from pydantic import BaseModel, Field

from app.ai.schemas import ResumeAnalysisResult
from app.models.recruitment import AnalysisStatus

ADVISORY_NOTICE = (
    "Advisory only. This score and summary are an aid for the recruiter. They never approve or reject anyone, "
    "and applicants cannot see them."
)


class AnalysisReportOut(BaseModel):
    id: int
    application_id: int
    resume_id: int
    resume_version: int
    status: AnalysisStatus
    provider: str
    model: str
    prompt_version: str
    is_mock: bool
    ai_score: int | None
    effective_score: int | None
    report: ResumeAnalysisResult | None
    error: str | None
    requested_by_name: str | None
    created_at: datetime
    override_score: int | None
    override_note: str | None
    overridden_by_name: str | None
    overridden_at: datetime | None


class AIStatusOut(BaseModel):
    provider: str
    model: str
    is_mock: bool
    configured: bool


class AnalysisOverview(BaseModel):
    ai: AIStatusOut
    notice: str = ADVISORY_NOTICE
    can_run: bool
    latest: AnalysisReportOut | None
    history: list[AnalysisReportOut]


class OverrideRequest(BaseModel):
    score: int = Field(ge=0, le=100)
    note: str = Field(min_length=3, max_length=2000)
