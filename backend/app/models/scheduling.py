"""Scheduling and online testing tables (Phase 5).

Design notes:
* A schedule pins a *published, immutable* assessment version; later edits never change what an applicant sees.
* The invitation token is stored only as a SHA-256 hash. The plaintext is emailed once.
* Client events (tab hidden, copy, paste...) are informational. Nothing here triggers rejection.
* Answer keys are never copied into attempt rows; they stay in the version snapshot.
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, enum_column


class ScheduleStatus(str, enum.Enum):
    INVITED = "invited"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ACTIVE_SCHEDULE_STATUSES = (ScheduleStatus.INVITED, ScheduleStatus.ACCEPTED, ScheduleStatus.IN_PROGRESS)


class RescheduleStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ALTERNATIVE_SUGGESTED = "alternative_suggested"
    ALTERNATIVE_ACCEPTED = "alternative_accepted"
    ALTERNATIVE_DECLINED = "alternative_declined"
    WITHDRAWN = "withdrawn"


class AttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


class AssessmentSchedule(TimestampMixin, Base):
    __tablename__ = "assessment_schedules"
    __table_args__ = (
        Index("ix_assessment_schedules_application_id", "application_id"),
        Index("ix_assessment_schedules_status", "status"),
        Index("ix_assessment_schedules_candidate_status", "candidate_id", "status"),
        Index("ix_assessment_schedules_token_hash", "token_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="RESTRICT"))
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id", ondelete="RESTRICT"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str | None] = mapped_column(Text)
    link_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScheduleStatus] = mapped_column(enum_column(ScheduleStatus, "schedule_status", 20), default=ScheduleStatus.INVITED)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class RescheduleRequest(TimestampMixin, Base):
    __tablename__ = "reschedule_requests"
    __table_args__ = (Index("ix_reschedule_requests_schedule_id", "schedule_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("assessment_schedules.id", ondelete="CASCADE"))
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(Text)
    preferred_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RescheduleStatus] = mapped_column(enum_column(RescheduleStatus, "reschedule_status", 24), default=RescheduleStatus.PENDING)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    new_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduleEvent(Base):
    """Append-only activity log for a schedule / attempt (separate from the global audit log)."""

    __tablename__ = "schedule_events"
    __table_args__ = (Index("ix_schedule_events_schedule_created", "schedule_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("assessment_schedules.id", ondelete="CASCADE"))
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # True for browser-reported events; these are informational and never automatic grounds for rejection.
    client_reported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestAttempt(TimestampMixin, Base):
    __test__ = False  # not a pytest class
    __tablename__ = "test_attempts"
    __table_args__ = (UniqueConstraint("schedule_id", name="uq_test_attempts_schedule_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("assessment_schedules.id", ondelete="CASCADE"))
    status: Mapped[AttemptStatus] = mapped_column(enum_column(AttemptStatus, "attempt_status", 20), default=AttemptStatus.IN_PROGRESS)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submit_reason: Mapped[str | None] = mapped_column(String(20))  # manual | timeout
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_id: Mapped[str] = mapped_column(String(64))
    # Per-attempt shuffle: {"sections": [{"kind", "questions": [{"question_id", "option_order": [orig idx...]}]}]}
    question_order: Mapped[dict] = mapped_column(JSONType)
    # {question_id: plays used} for Repeat-the-Sentence audio
    plays: Mapped[dict] = mapped_column(JSONType, default=dict)


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_answers_attempt_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(Integer)  # id inside the pinned version snapshot
    selected_index: Mapped[int | None] = mapped_column(Integer)  # index in the ORIGINAL option list
    marked_for_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AttemptRecording(Base):
    """Private audio for one Repeat-the-Sentence recording attempt. Only an opaque stored name is kept."""

    __tablename__ = "attempt_recordings"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", "attempt_no", name="uq_attempt_recordings_attempt_question_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(Integer)
    stored_name: Mapped[str] = mapped_column(String(100))
    mime: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    is_final: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
