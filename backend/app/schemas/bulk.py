from datetime import datetime

from pydantic import BaseModel, Field

from app.models.bulk import BulkItemStatus, ScreeningStatus


class Progress(BaseModel):
    queued: int
    processing: int
    done: int
    failed: int
    total: int
    finished: int
    complete: bool


class BatchOut(BaseModel):
    id: int
    name: str
    opening_id: int
    opening_title: str
    created_by_name: str | None
    created_at: datetime
    ai_provider: str | None
    ai_is_mock: bool | None
    progress: Progress


class RejectedFile(BaseModel):
    filename: str
    reason: str


class BatchCreated(BaseModel):
    batch: BatchOut
    rejected: list[RejectedFile]


class ItemOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    status: BulkItemStatus
    error: str | None
    attempts: int
    candidate_name: str | None
    email: str | None
    phone: str | None
    skills: list[str]
    experience_years: float | None
    match_score: int | None
    duplicate_kind: str | None
    duplicate_of_item_id: int | None
    existing_applicant: bool
    existing_application_id: int | None
    review_status: ScreeningStatus
    review_note: str | None
    warnings: list[str]


class ItemDetail(ItemOut):
    education: list[str]
    analysis: dict | None


class TriageIn(BaseModel):
    status: ScreeningStatus
    note: str | None = Field(default=None, max_length=1000)
