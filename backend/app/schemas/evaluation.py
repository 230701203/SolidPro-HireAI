from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.evaluation import EvaluationStatus, SttStatus


class OverrideIn(BaseModel):
    marks: float = Field(ge=0, le=1000)
    reason: str = Field(min_length=5, max_length=1000)


class ConfirmIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ReleaseIn(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)  # shown to the applicant: keep it constructive


class DecisionIn(BaseModel):
    decision: Literal["shortlist", "select", "reject"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _reason(self):
        if self.decision == "reject" and not (self.reason and len(self.reason.strip()) >= 5):
            raise ValueError("Give a reason when rejecting a candidate")
        return self


class SpeechView(BaseModel):
    expected: str
    recognized: str
    confidence: float | None
    accuracy: float | None
    completeness: float | None
    missing: list[str]
    substituted: list[dict]
    near_matches: list[dict]
    extra: list[str]
    order_differs: bool
    provider: str | None
    is_mock: bool
    error: str | None


class RecordingRef(BaseModel):
    id: int
    attempt_no: int
    is_final: bool


class ItemOut(BaseModel):
    id: int
    question_id: int
    section: str
    position: int
    text: str
    options: list[str] | None
    selected_index: int | None
    selected_text: str | None
    correct_index: int | None
    correct_text: str | None
    is_correct: bool | None
    unanswered: bool
    max_marks: float
    auto_marks: float | None
    final_marks: float | None
    overridden: bool
    needs_review: bool
    review_note: str | None
    stt_status: SttStatus
    speech: SpeechView | None
    recordings: list[RecordingRef]


class ItemGroup(BaseModel):
    kind: str
    title: str
    items: list[ItemOut]


class SectionScore(BaseModel):
    kind: str
    title: str
    obtained: float
    total: float
    correct: int
    incorrect: int
    unanswered: int
    unresolved: int  # items without a final score yet


class OverrideOut(BaseModel):
    id: int
    item_id: int
    question_position: int
    section: str
    original_marks: float | None
    revised_marks: float
    reason: str
    changed_by: str | None
    changed_at: datetime


class CommentOut(BaseModel):
    id: int
    author: str | None
    body: str
    created_at: datetime


class EvaluationListItem(BaseModel):
    id: int
    application_id: int
    schedule_id: int
    candidate_name: str
    opening_title: str
    test_date: datetime | None
    status: EvaluationStatus
    total_marks: float
    total_obtained: float
    percentage: float | None
    unresolved: int
    released: bool
    application_status: str


class EvaluationDetail(EvaluationListItem):
    candidate_email: str
    assessment_title: str
    assessment_is_mock: bool
    duration_minutes: int
    time_taken_seconds: int | None
    summary: str | None
    sections: list[SectionScore]
    groups: list[ItemGroup]
    overrides: list[OverrideOut]
    comments: list[CommentOut]
    blockers: list[str]
    can_edit: bool
    speech_provider: str | None
    speech_is_mock: bool
    applicant_feedback: str | None
    finalized_at: datetime | None
    released_at: datetime | None


class MySection(BaseModel):
    kind: str
    title: str
    obtained: float
    total: float


class MyResult(BaseModel):
    id: int
    application_id: int
    opening_title: str
    assessment_title: str
    test_date: datetime | None
    released_at: datetime
    total_marks: float
    total_obtained: float
    percentage: float | None
    sections: list[MySection]
    time_taken_seconds: int | None
    feedback: str | None
