import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    ApplicationStatus,
    EmploymentType,
    ExperienceKind,
    OpeningStatus,
    SkillKind,
    WorkMode,
)

_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def _clean_list(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for v in values:
        v = v.strip()
        if v:
            if len(v) > 100:
                raise ValueError("Each skill must be at most 100 characters")
            seen.setdefault(v.lower(), v)
    if len(seen) > 60:
        raise ValueError("Too many skills (max 60)")
    return list(seen.values())


# ------------------------------------------------------------------ categories


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_internship: bool = False

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Name is too short")
        return v


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_internship: bool | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    is_internship: bool
    is_active: bool
    openings_count: int = 0


# ------------------------------------------------------------------ openings


class OpeningBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category_id: int
    description: str = Field(min_length=10, max_length=20000)
    responsibilities: str | None = Field(default=None, max_length=20000)
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    required_qualifications: str | None = Field(default=None, max_length=5000)
    preferred_qualifications: str | None = Field(default=None, max_length=5000)
    required_experience: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType
    work_mode: WorkMode
    location: str | None = Field(default=None, max_length=150)
    vacancies: int = Field(default=1, ge=1, le=1000)
    deadline: date | None = None
    intern_college: str | None = Field(default=None, max_length=200)
    intern_degree: str | None = Field(default=None, max_length=100)
    intern_department: str | None = Field(default=None, max_length=100)
    intern_graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    intern_duration: str | None = Field(default=None, max_length=100)
    intern_availability: str | None = Field(default=None, max_length=150)
    intern_stipend: str | None = Field(default=None, max_length=100)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return " ".join(v.split())


class OpeningCreate(OpeningBase):
    assigned_employee_ids: list[int] = []


class OpeningUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    title: str | None = Field(default=None, min_length=3, max_length=200)
    category_id: int | None = None
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    responsibilities: str | None = Field(default=None, max_length=20000)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    required_qualifications: str | None = Field(default=None, max_length=5000)
    preferred_qualifications: str | None = Field(default=None, max_length=5000)
    required_experience: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    location: str | None = Field(default=None, max_length=150)
    vacancies: int | None = Field(default=None, ge=1, le=1000)
    deadline: date | None = None
    intern_college: str | None = Field(default=None, max_length=200)
    intern_degree: str | None = Field(default=None, max_length=100)
    intern_department: str | None = Field(default=None, max_length=100)
    intern_graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    intern_duration: str | None = Field(default=None, max_length=100)
    intern_availability: str | None = Field(default=None, max_length=150)
    intern_stipend: str | None = Field(default=None, max_length=100)
    assigned_employee_ids: list[int] | None = None

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_list(v)


class AssigneeOut(BaseModel):
    id: int
    full_name: str
    email: str


class OpeningListItem(BaseModel):
    id: int
    title: str
    category_id: int
    category_name: str
    status: OpeningStatus
    employment_type: EmploymentType
    work_mode: WorkMode
    location: str | None
    vacancies: int
    deadline: date | None
    is_open: bool
    applications_count: int
    pending_count: int
    assignees: list[AssigneeOut]
    created_at: datetime


class OpeningOut(OpeningBase):
    id: int
    status: OpeningStatus
    category_name: str
    category_is_internship: bool
    is_open: bool
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    created_by_name: str | None
    applications_count: int
    assignees: list[AssigneeOut]


class PublicJobOut(BaseModel):
    """What an applicant may see. No assignees, no internal fields."""

    id: int
    title: str
    category_name: str
    description: str
    responsibilities: str | None
    required_skills: list[str]
    preferred_skills: list[str]
    required_qualifications: str | None
    preferred_qualifications: str | None
    required_experience: str | None
    employment_type: EmploymentType
    work_mode: WorkMode
    location: str | None
    vacancies: int
    deadline: date | None
    published_at: datetime | None
    is_internship: bool
    intern_college: str | None
    intern_degree: str | None
    intern_department: str | None
    intern_graduation_year: int | None
    intern_duration: str | None
    intern_availability: str | None
    intern_stipend: str | None
    applied: bool = False
    application_id: int | None = None


# ------------------------------------------------------------------ candidate profile


class EducationIn(BaseModel):
    degree: str = Field(min_length=2, max_length=150)
    institution: str = Field(min_length=2, max_length=200)
    department: str | None = Field(default=None, max_length=150)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    grade: str | None = Field(default=None, max_length=50)


class EducationOut(EducationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ExperienceIn(BaseModel):
    kind: ExperienceKind
    organization: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=2, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = Field(default=None, max_length=3000)

    @field_validator("end_date")
    @classmethod
    def _order(cls, v: date | None, info) -> date | None:
        start = info.data.get("start_date")
        if v and start and v < start:
            raise ValueError("End date cannot be before the start date")
        return v


class ExperienceOut(ExperienceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: SkillKind


class SkillOut(SkillIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProfileIn(BaseModel):
    date_of_birth: date | None = None
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=300)
    portfolio_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    highest_qualification: str | None = Field(default=None, max_length=150)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    education: list[EducationIn] = Field(default=[], max_length=20)
    experience: list[ExperienceIn] = Field(default=[], max_length=40)
    skills: list[SkillIn] = Field(default=[], max_length=120)

    @field_validator("linkedin_url", "portfolio_url", "github_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _URL_RE.match(v):
            raise ValueError("Enter a full URL starting with http:// or https://")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        if v and (v > date.today() or v.year < 1930):
            raise ValueError("Enter a valid date of birth")
        return v


class ResumeOut(BaseModel):
    id: int
    version: int
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    is_current: bool = False


class ProfileOut(BaseModel):
    candidate_id: int
    user_id: int
    full_name: str
    email: str
    mobile: str | None
    date_of_birth: date | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    linkedin_url: str | None
    portfolio_url: str | None
    github_url: str | None
    highest_qualification: str | None
    total_experience_years: float | None
    education: list[EducationOut]
    experience: list[ExperienceOut]
    skills: list[SkillOut]
    resumes: list[ResumeOut]
    completion: int
    missing: list[str]


class ApplicantListItem(BaseModel):
    candidate_id: int
    user_id: int
    full_name: str
    email: str
    mobile: str | None
    city: str | None
    highest_qualification: str | None
    applications_count: int
    created_at: datetime


# ------------------------------------------------------------------ applications


class ApplyRequest(BaseModel):
    opening_id: int
    resume_id: int | None = None
    cover_note: str | None = Field(default=None, max_length=3000)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class MessageRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)


class OptionalNoteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class RespondRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    resume_id: int | None = None


class HistoryOut(BaseModel):
    id: int
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    comment: str | None
    actor_name: str | None
    actor_role: str | None
    visible_to_applicant: bool
    created_at: datetime


class ApplicationListItem(BaseModel):
    id: int
    status: ApplicationStatus
    opening_id: int
    opening_title: str
    category_name: str
    candidate_id: int
    candidate_name: str
    candidate_email: str
    submitted_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationListItem):
    cover_note: str | None
    resume: ResumeOut
    decision_reason: str | None
    decided_at: datetime | None
    decided_by_name: str | None
    history: list[HistoryOut]
    can_review: bool = False
    # Staff only (None for the applicant): required skills versus what the profile lists is Phase 3 (AI)
    candidate: ProfileOut | None = None
