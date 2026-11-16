"""Assessment tables (Phase 4).

Design notes:
* An assessment always has exactly three sections: MCQ, Aptitude, Repeat the Sentence.
* Questions live on the assessment as copies. Editing the reusable bank never changes an assessment.
* `assessment_versions` rows are immutable snapshots created at approval; a database trigger enforces it.
* Options are stored as a JSON list on the question row (a separate options table adds no value here).
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, enum_column


class AssessmentStatus(str, enum.Enum):
    DRAFT = "draft"  # has content not yet approved
    APPROVED = "approved"  # current content equals the latest approved version


class SectionKind(str, enum.Enum):
    MCQ = "mcq"
    APTITUDE = "aptitude"
    REPEAT_SENTENCE = "repeat_sentence"


class QuestionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class QuestionSource(str, enum.Enum):
    AI = "ai"
    TEMPLATE = "template"  # curated mock content
    BANK = "bank"
    MANUAL = "manual"


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


APTITUDE_TOPICS = ("numerical", "logical", "analytical", "verbal", "data_interpretation", "pattern")


class QuestionBank(TimestampMixin, Base):
    __tablename__ = "question_banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("job_categories.id", ondelete="SET NULL"))  # null = all roles
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class BankQuestion(TimestampMixin, Base):
    """Reusable aptitude question with a verified answer key."""

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_bank_id", "bank_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("question_banks.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSONType)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(enum_column(Difficulty, "bank_difficulty", 10))
    marks: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | seed
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Assessment(TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (Index("ix_assessments_application_id", "application_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[AssessmentStatus] = mapped_column(enum_column(AssessmentStatus, "assessment_status", 12), default=AssessmentStatus.DRAFT)
    difficulty: Mapped[Difficulty] = mapped_column(enum_column(Difficulty, "assessment_difficulty", 10), default=Difficulty.MEDIUM)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    config: Mapped[dict] = mapped_column(JSONType)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_notes: Mapped[list | None] = mapped_column(JSONType)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AssessmentSection(Base):
    __tablename__ = "assessment_sections"
    __table_args__ = (UniqueConstraint("assessment_id", "kind", name="uq_assessment_sections_assessment_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    kind: Mapped[SectionKind] = mapped_column(enum_column(SectionKind, "section_kind", 20))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100))


class AssessmentQuestion(TimestampMixin, Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (Index("ix_assessment_questions_assessment_id", "assessment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("assessment_sections.id", ondelete="CASCADE"))
    kind: Mapped[SectionKind] = mapped_column(enum_column(SectionKind, "question_kind", 20))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[QuestionStatus] = mapped_column(enum_column(QuestionStatus, "question_status", 10), default=QuestionStatus.PENDING)
    source: Mapped[QuestionSource] = mapped_column(enum_column(QuestionSource, "question_source", 10))
    bank_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)  # for Repeat the Sentence this is the expected sentence
    options: Mapped[list | None] = mapped_column(JSONType)
    correct_index: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(enum_column(Difficulty, "question_difficulty", 10), default=Difficulty.MEDIUM)
    topic: Mapped[str | None] = mapped_column(String(100))
    skill: Mapped[str | None] = mapped_column(String(100))
    q_type: Mapped[str | None] = mapped_column(String(30))
    marks: Mapped[int] = mapped_column(Integer, default=1)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)


class AssessmentVersion(Base):
    """Immutable approved snapshot. Scheduling and testing (Phase 5) use these rows, never the editable draft."""

    __tablename__ = "assessment_versions"
    __table_args__ = (UniqueConstraint("assessment_id", "version", name="uq_assessment_versions_assessment_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONType)
    content_hash: Mapped[str] = mapped_column(String(64))
    total_marks: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AssessmentApproval(Base):
    __tablename__ = "assessment_approvals"
    __table_args__ = (Index("ix_assessment_approvals_assessment_id", "assessment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="RESTRICT"))
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(20), default="approved")
    note: Mapped[str | None] = mapped_column(Text)
    question_ids: Mapped[list] = mapped_column(JSONType)
    changes: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
