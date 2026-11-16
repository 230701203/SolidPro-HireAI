"""Bulk resume screening (Phase 7).

Design decisions:
* A bulk batch is a *screening* tool. It never creates user accounts and never edits an existing applicant's profile
  from someone else's resume: the people in a batch have not registered and have not consented to an account.
* Duplicates are detected (existing applicant by email, same email or same file inside the batch) and linked, not merged.
* Extracted fields are heuristics and are labelled as such; scores are advisory.
* Files are stored privately; a batch can be deleted completely (rows and files).
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, enum_column


class BulkItemStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ScreeningStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    INTERESTING = "interesting"
    NOT_SUITABLE = "not_suitable"


class BulkBatch(TimestampMixin, Base):
    __tablename__ = "bulk_batches"
    __table_args__ = (Index("ix_bulk_batches_opening_id", "opening_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    opening_id: Mapped[int] = mapped_column(ForeignKey("job_openings.id", ondelete="CASCADE"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(150))
    ai_provider: Mapped[str | None] = mapped_column(String(30))
    ai_is_mock: Mapped[bool | None] = mapped_column()


class BulkItem(TimestampMixin, Base):
    __tablename__ = "bulk_items"
    __table_args__ = (
        Index("ix_bulk_items_batch_status", "batch_id", "status"),
        Index("ix_bulk_items_email", "email"),
        Index("ix_bulk_items_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("bulk_batches.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(200))
    stored_name: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[BulkItemStatus] = mapped_column(enum_column(BulkItemStatus, "bulk_item_status", 12), default=BulkItemStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # extracted (heuristic) fields
    candidate_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    skills: Mapped[list | None] = mapped_column(JSONType)
    experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1, asdecimal=False))
    education: Mapped[list | None] = mapped_column(JSONType)
    warnings: Mapped[list | None] = mapped_column(JSONType)
    # analysis (advisory)
    match_score: Mapped[int | None] = mapped_column(Integer)
    analysis: Mapped[dict | None] = mapped_column(JSONType)
    # duplicates
    duplicate_kind: Mapped[str | None] = mapped_column(String(30))  # existing_applicant | duplicate_in_batch | duplicate_file
    existing_candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="SET NULL"))
    duplicate_of_item_id: Mapped[int | None] = mapped_column(ForeignKey("bulk_items.id", ondelete="SET NULL"))
    # human triage (has no effect on any applicant)
    review_status: Mapped[ScreeningStatus] = mapped_column(enum_column(ScreeningStatus, "screening_status", 14), default=ScreeningStatus.UNREVIEWED)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
