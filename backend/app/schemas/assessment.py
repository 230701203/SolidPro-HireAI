from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.assessment import APTITUDE_TOPICS, AssessmentStatus, Difficulty, QuestionSource, QuestionStatus, SectionKind

Topic = Literal["numerical", "logical", "analytical", "verbal", "data_interpretation", "pattern"]


def _clean_options(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    return [str(o).strip() for o in v]


class OptionsMixin(BaseModel):
    @model_validator(mode="after")
    def _opts(self):
        opts = getattr(self, "options", None)
        ci = getattr(self, "correct_index", None)
        if opts is not None:
            if not 2 <= len(opts) <= 6:
                raise ValueError("Provide between 2 and 6 answer options")
            if any(not o for o in opts):
                raise ValueError("Answer options cannot be empty")
            if len({o.lower() for o in opts}) != len(opts):
                raise ValueError("Answer options must be different from each other")
            if ci is not None and not 0 <= ci < len(opts):
                raise ValueError("The correct answer must be one of the options")
        return self


# ---------------------------------------------------------------- question bank


class BankCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category_id: int | None = None


class BankUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category_id: int | None = None
    is_active: bool | None = None


class BankOut(BaseModel):
    id: int
    name: str
    description: str | None
    category_id: int | None
    category_name: str | None
    is_active: bool
    question_count: int
    active_question_count: int


class BankQuestionIn(OptionsMixin):
    topic: Topic
    text: str = Field(min_length=10, max_length=2000)
    options: list[str]
    correct_index: int = Field(ge=0)
    explanation: str | None = Field(default=None, max_length=2000)
    difficulty: Difficulty = Difficulty.MEDIUM
    marks: int = Field(default=1, ge=1, le=10)

    @field_validator("options", mode="before")
    @classmethod
    def _o(cls, v):
        return _clean_options(v)


class BankQuestionUpdate(OptionsMixin):
    topic: Topic | None = None
    text: str | None = Field(default=None, min_length=10, max_length=2000)
    options: list[str] | None = None
    correct_index: int | None = Field(default=None, ge=0)
    explanation: str | None = Field(default=None, max_length=2000)
    difficulty: Difficulty | None = None
    marks: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _o(cls, v):
        return _clean_options(v)


class BankQuestionOut(BaseModel):
    id: int
    bank_id: int
    topic: str
    text: str
    options: list[str]
    correct_index: int
    explanation: str | None
    difficulty: Difficulty
    marks: int
    is_active: bool
    source: str
    verified_by_name: str | None
    updated_at: datetime


# ---------------------------------------------------------------- assessments


class AssessmentConfig(BaseModel):
    mcq_count: int = Field(default=10, ge=1, le=40)
    mcq_marks: int = Field(default=1, ge=1, le=10)
    aptitude_count: int = Field(default=6, ge=1, le=30)
    aptitude_marks: int = Field(default=1, ge=1, le=10)
    aptitude_topics: list[Topic] = Field(default_factory=lambda: list(APTITUDE_TOPICS), min_length=1)
    rs_count: int = Field(default=5, ge=1, le=15)
    rs_marks: int = Field(default=2, ge=1, le=10)
    rs_max_replays: int = Field(default=1, ge=0, le=3)
    rs_max_attempts: int = Field(default=1, ge=1, le=3)
    rs_record_seconds: int = Field(default=20, ge=5, le=60)


class GenerateRequest(BaseModel):
    application_id: int
    title: str | None = Field(default=None, max_length=200)
    difficulty: Difficulty = Difficulty.MEDIUM
    duration_minutes: int = Field(default=45, ge=10, le=240)
    config: AssessmentConfig = Field(default_factory=AssessmentConfig)


class AssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    difficulty: Difficulty | None = None
    duration_minutes: int | None = Field(default=None, ge=10, le=240)
    config: AssessmentConfig | None = None


class QuestionCreate(OptionsMixin):
    section: SectionKind
    text: str = Field(min_length=5, max_length=2000)
    options: list[str] | None = None
    correct_index: int | None = Field(default=None, ge=0)
    explanation: str | None = Field(default=None, max_length=2000)
    difficulty: Difficulty = Difficulty.MEDIUM
    topic: str | None = Field(default=None, max_length=100)
    skill: str | None = Field(default=None, max_length=100)
    marks: int = Field(default=1, ge=1, le=10)

    @field_validator("options", mode="before")
    @classmethod
    def _o(cls, v):
        return _clean_options(v)

    @model_validator(mode="after")
    def _kind_rules(self):
        if self.section == SectionKind.REPEAT_SENTENCE:
            if self.options or self.correct_index is not None:
                raise ValueError("Repeat the Sentence questions have a sentence only, no options")
        else:
            if self.options is None or self.correct_index is None:
                raise ValueError("Provide the answer options and mark the correct one")
        return self


class QuestionUpdate(OptionsMixin):
    text: str | None = Field(default=None, min_length=5, max_length=2000)
    options: list[str] | None = None
    correct_index: int | None = Field(default=None, ge=0)
    explanation: str | None = Field(default=None, max_length=2000)
    difficulty: Difficulty | None = None
    topic: str | None = Field(default=None, max_length=100)
    skill: str | None = Field(default=None, max_length=100)
    marks: int | None = Field(default=None, ge=1, le=10)

    @field_validator("options", mode="before")
    @classmethod
    def _o(cls, v):
        return _clean_options(v)


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class QuestionOut(BaseModel):
    id: int
    section: SectionKind
    position: int
    status: QuestionStatus
    source: QuestionSource
    text: str
    options: list[str] | None
    correct_index: int | None
    explanation: str | None
    difficulty: Difficulty
    topic: str | None
    skill: str | None
    q_type: str | None
    marks: int
    edited: bool
    is_placeholder: bool
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    reject_reason: str | None


class SectionOut(BaseModel):
    id: int
    kind: SectionKind
    title: str
    total_marks: int
    questions: list[QuestionOut]


class VersionOut(BaseModel):
    id: int
    version: int
    total_marks: int
    duration_minutes: int
    content_hash: str
    approved_by_name: str | None
    approved_at: datetime
    published_at: datetime | None
    published_by_name: str | None


class ApprovalOut(BaseModel):
    id: int
    version: int
    reviewer_name: str | None
    decision: str
    note: str | None
    question_ids: list[int]
    changes: dict
    created_at: datetime


class AIInfo(BaseModel):
    provider: str
    model: str
    is_mock: bool
    prompt_version: str


class AssessmentDetail(BaseModel):
    id: int
    application_id: int
    candidate_name: str
    opening_title: str
    title: str
    status: AssessmentStatus
    difficulty: Difficulty
    duration_minutes: int
    config: AssessmentConfig
    ai: AIInfo
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
    sections: list[SectionOut]
    total_marks: int
    counts: dict[str, int]
    blockers: list[str]
    has_unapproved_changes: bool
    latest_version: int | None
    published_version: int | None
    versions: list[VersionOut]
    approvals: list[ApprovalOut]
    generation_notes: list[str]
    can_edit: bool
    can_generate: bool
    notice: str


class AssessmentListItem(BaseModel):
    id: int
    application_id: int
    candidate_name: str
    opening_title: str
    title: str
    status: AssessmentStatus
    is_mock: bool
    total_marks: int
    question_count: int
    pending_count: int
    latest_version: int | None
    published_version: int | None
    created_at: datetime


class FromBankRequest(BaseModel):
    bank_question_id: int


class VersionDetail(BaseModel):
    version: int
    content_hash: str
    integrity_ok: bool
    total_marks: int
    duration_minutes: int
    approved_by_name: str | None
    approved_at: datetime
    published_at: datetime | None
    snapshot: dict
