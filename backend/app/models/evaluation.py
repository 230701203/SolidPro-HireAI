"""Evaluation, review and release (Phase 6) and interviews.

Principles: scores are computed from the *pinned immutable snapshot*; speech scores are advisory and flagged when the
transcript is uncertain; every manual score change is recorded; nothing reaches the applicant until a reviewer
finalises and releases it.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, enum_column


class EvaluationStatus(str, enum.Enum):
    DRAFT = "draft"  # auto-evaluated, a reviewer is still working
    FINAL = "final"  # approved by a reviewer


class SttStatus(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    OK = "ok"
    LOW_CONFIDENCE = "low_confidence"
    FAILED = "failed"
    NO_RECORDING = "no_recording"


class InterviewStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"


class InterviewType(str, enum.Enum):
    TECHNICAL = "technical"
    HR = "hr"
    MANAGERIAL = "managerial"
    PANEL = "panel"
    OTHER = "other"


class InterviewMode(str, enum.Enum):
    ONLINE = "online"
    ONSITE = "onsite"
    PHONE = "phone"


class Recommendation(str, enum.Enum):
    STRONG_YES = "strong_yes"
    YES = "yes"
    NEUTRAL = "neutral"
    NO = "no"
    STRONG_NO = "strong_no"


Marks = Numeric(7, 2, asdecimal=False)


class EvaluationResult(TimestampMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_evaluation_results_attempt_id"),
        Index("ix_evaluation_results_application_id", "application_id"),
        Index("ix_evaluation_results_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"))
    schedule_id: Mapped[int] = mapped_column(ForeignKey("assessment_schedules.id", ondelete="CASCADE"))
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    status: Mapped[EvaluationStatus] = mapped_column(enum_column(EvaluationStatus, "evaluation_status", 10), default=EvaluationStatus.DRAFT)
    # Denormalised totals (recomputed on every change) for list views
    total_marks: Mapped[float] = mapped_column(Marks, default=0)
    total_obtained: Mapped[float] = mapped_column(Marks, default=0)
    percentage: Mapped[float | None] = mapped_column(Float)
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)  # rules-based performance summary (NOT AI-written)
    speech_provider: Mapped[str | None] = mapped_column(String(30))
    speech_is_mock: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applicant_feedback: Mapped[str | None] = mapped_column(Text)  # the only free text an applicant ever sees


class EvaluationItem(Base):
    __tablename__ = "evaluation_items"
    __table_args__ = (UniqueConstraint("evaluation_id", "question_id", name="uq_evaluation_items_evaluation_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation_results.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer)
    max_marks: Mapped[float] = mapped_column(Marks)
    auto_marks: Mapped[float | None] = mapped_column(Marks)  # None = could not be scored automatically
    final_marks: Mapped[float | None] = mapped_column(Marks)  # auto unless overridden
    selected_index: Mapped[int | None] = mapped_column(Integer)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    unanswered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    stt_status: Mapped[SttStatus] = mapped_column(enum_column(SttStatus, "stt_status", 20), default=SttStatus.NOT_APPLICABLE)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONType)  # speech comparison, transcript, flags
    overridden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class ScoreOverride(Base):
    """Every manual score change: who, when, original, revised, why."""

    __tablename__ = "score_overrides"
    __table_args__ = (Index("ix_score_overrides_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation_results.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("evaluation_items.id", ondelete="CASCADE"))
    original_marks: Mapped[float | None] = mapped_column(Marks)
    revised_marks: Mapped[float] = mapped_column(Marks)
    reason: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationComment(Base):
    """Internal reviewer comments. Never shown to applicants."""

    __tablename__ = "evaluation_comments"
    __table_args__ = (Index("ix_evaluation_comments_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation_results.id", ondelete="CASCADE"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecordingTranscript(Base):
    __tablename__ = "recording_transcripts"
    __table_args__ = (UniqueConstraint("recording_id", name="uq_recording_transcripts_recording_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("attempt_recordings.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"
    __table_args__ = (Index("ix_interviews_application_id", "application_id"), Index("ix_interviews_interviewer_id", "interviewer_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    interviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    interview_type: Mapped[InterviewType] = mapped_column(enum_column(InterviewType, "interview_type", 12), default=InterviewType.TECHNICAL)
    mode: Mapped[InterviewMode] = mapped_column(enum_column(InterviewMode, "interview_mode", 10), default=InterviewMode.ONLINE)
    status: Mapped[InterviewStatus] = mapped_column(enum_column(InterviewStatus, "interview_status", 12), default=InterviewStatus.PENDING)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    meeting_link: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(300))
    instructions: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InterviewFeedback(TimestampMixin, Base):
    """Internal. Never shown to applicants."""

    __tablename__ = "interview_feedback"
    __table_args__ = (UniqueConstraint("interview_id", name="uq_interview_feedback_interview_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    technical_feedback: Mapped[str | None] = mapped_column(Text)
    communication_feedback: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    improvements: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[Recommendation] = mapped_column(enum_column(Recommendation, "interview_recommendation", 12))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
