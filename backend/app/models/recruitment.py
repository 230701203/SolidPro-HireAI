import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, enum_column
from app.models.user import CandidateProfile


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"


class WorkMode(str, enum.Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class OpeningStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ApplicationStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    INFO_REQUESTED = "info_requested"
    APPROVED = "approved"  # approved for assessment
    SHORTLISTED = "shortlisted"  # after a finalised evaluation (Phase 6)
    SELECTED = "selected"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SkillKind(str, enum.Enum):
    TECHNICAL = "technical"
    SOFT = "soft"
    TOOL = "tool"
    CERTIFICATION = "certification"


class ExperienceKind(str, enum.Enum):
    JOB = "job"
    INTERNSHIP = "internship"
    PROJECT = "project"


# ------------------------------------------------------------------ job categories & openings


class JobCategory(TimestampMixin, Base):
    """Recruitment category (CAD, Digital Transform, Intern, ...). NOT an account type."""

    __tablename__ = "job_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_internship: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class JobOpening(TimestampMixin, Base):
    __tablename__ = "job_openings"
    __table_args__ = (
        Index("ix_job_openings_status_deadline", "status", "deadline"),
        Index("ix_job_openings_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("job_categories.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    required_skills: Mapped[list] = mapped_column(JSONType, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONType, default=list)
    required_qualifications: Mapped[str | None] = mapped_column(Text)
    preferred_qualifications: Mapped[str | None] = mapped_column(Text)
    required_experience: Mapped[str | None] = mapped_column(String(100))
    employment_type: Mapped[EmploymentType] = mapped_column(enum_column(EmploymentType, "employment_type", 16))
    work_mode: Mapped[WorkMode] = mapped_column(enum_column(WorkMode, "work_mode", 16))
    location: Mapped[str | None] = mapped_column(String(150))
    vacancies: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[OpeningStatus] = mapped_column(enum_column(OpeningStatus, "opening_status", 16), default=OpeningStatus.DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Internship-specific
    intern_college: Mapped[str | None] = mapped_column(String(200))
    intern_degree: Mapped[str | None] = mapped_column(String(100))
    intern_department: Mapped[str | None] = mapped_column(String(100))
    intern_graduation_year: Mapped[int | None] = mapped_column(Integer)
    intern_duration: Mapped[str | None] = mapped_column(String(100))
    intern_availability: Mapped[str | None] = mapped_column(String(150))
    intern_stipend: Mapped[str | None] = mapped_column(String(100))

    category: Mapped[JobCategory] = relationship()


class EmployeeAssignment(Base):
    __tablename__ = "employee_assignments"

    opening_id: Mapped[int] = mapped_column(ForeignKey("job_openings.id", ondelete="CASCADE"), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_employee_assignments_employee_id", "employee_id"),)


# ------------------------------------------------------------------ candidate profile parts


class CandidateEducation(Base):
    __tablename__ = "candidate_education"
    __table_args__ = (Index("ix_candidate_education_candidate_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    degree: Mapped[str] = mapped_column(String(150))
    institution: Mapped[str] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(150))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(50))  # CGPA or percentage


class CandidateExperience(Base):
    __tablename__ = "candidate_experience"
    __table_args__ = (Index("ix_candidate_experience_candidate_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    kind: Mapped[ExperienceKind] = mapped_column(enum_column(ExperienceKind, "experience_kind", 16))
    organization: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (
        UniqueConstraint("candidate_id", "kind", "name", name="uq_candidate_skills_candidate_kind_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    kind: Mapped[SkillKind] = mapped_column(enum_column(SkillKind, "skill_kind", 16))
    name: Mapped[str] = mapped_column(String(100))


class CandidateResume(Base):
    """Every upload is a new immutable version. Applications point at the exact version used."""

    __tablename__ = "candidate_resumes"
    __table_args__ = (UniqueConstraint("candidate_id", "version", name="uq_candidate_resumes_candidate_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)  # opaque; never exposed to clients
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    extracted_text: Mapped[str | None] = mapped_column(Text)  # input for AI analysis in Phase 3
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------------ applications


class JobApplication(TimestampMixin, Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "opening_id", name="uq_job_applications_candidate_opening"),
        Index("ix_job_applications_opening_status", "opening_id", "status"),
        Index("ix_job_applications_created_at", "created_at"),
        Index("ix_job_applications_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    opening_id: Mapped[int] = mapped_column(ForeignKey("job_openings.id", ondelete="RESTRICT"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("candidate_resumes.id", ondelete="RESTRICT"))
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_status", 20), default=ApplicationStatus.SUBMITTED
    )
    cover_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["CandidateProfile"] = relationship()
    opening: Mapped[JobOpening] = relationship()
    resume: Mapped[CandidateResume] = relationship()


class ApplicationStatusHistory(Base):
    """Timeline. from == to marks a comment-only entry."""

    __tablename__ = "application_status_history"
    __table_args__ = (
        Index("ix_application_status_history_application_id", "application_id"),
        Index("ix_application_status_history_to_status", "to_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    from_status: Mapped[ApplicationStatus | None] = mapped_column(enum_column(ApplicationStatus, "history_from_status", 20))
    to_status: Mapped[ApplicationStatus] = mapped_column(enum_column(ApplicationStatus, "history_to_status", 20))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(Text)
    # Internal reviewer notes are never shown to the applicant; decisions and requests are.
    visible_to_applicant: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



# ------------------------------------------------------------------ AI resume analysis


class AnalysisStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class ResumeAnalysisReport(Base):
    """One AI run for one application. Advisory only: it never changes the application status.

    Every run is kept (history). A reviewer may override the score; the AI's own score is never overwritten.
    """

    __tablename__ = "resume_analysis_reports"
    __table_args__ = (Index("ix_resume_analysis_reports_application_id", "application_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("candidate_resumes.id", ondelete="RESTRICT"))
    status: Mapped[AnalysisStatus] = mapped_column(enum_column(AnalysisStatus, "analysis_status", 12))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_score: Mapped[int | None] = mapped_column(Integer)
    report: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    override_score: Mapped[int | None] = mapped_column(Integer)
    override_note: Mapped[str | None] = mapped_column(Text)
    overridden_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
