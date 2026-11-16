from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PROMPT_VERSION = "resume-analysis-v1"
GENERATION_PROMPT_VERSION = "assessment-generation-v1"


@dataclass
class AnalysisInput:
    """Everything a provider may see. Deliberately excludes name, contact details, date of birth and address."""

    job_title: str
    job_description: str
    required_skills: list[str]
    preferred_skills: list[str]
    required_qualifications: str | None
    required_experience: str | None
    candidate_experience_years: float | None
    candidate_education: list[dict] = field(default_factory=list)
    candidate_skills: list[str] = field(default_factory=list)
    resume_text: str = ""


def _short_list(v: list[str], max_items: int = 12, max_len: int = 300) -> list[str]:
    return [str(x).strip()[:max_len] for x in (v or []) if str(x).strip()][:max_items]


class ResumeAnalysisResult(BaseModel):
    """Validated provider output. Scores are advisory and are clamped to 0-100."""

    match_score: int = Field(ge=0, le=100)
    confidence: Literal["low", "medium", "high"]
    summary: str = Field(max_length=1500)
    matched_required_skills: list[str] = []
    missing_required_skills: list[str] = []
    matched_preferred_skills: list[str] = []
    experience_assessment: str = Field(default="", max_length=1000)
    education_assessment: str = Field(default="", max_length=1000)
    strengths: list[str] = []
    gaps: list[str] = []
    clarifications_to_verify: list[str] = []
    suggested_interview_topics: list[str] = []

    @field_validator(
        "matched_required_skills", "missing_required_skills", "matched_preferred_skills", "strengths", "gaps",
        "clarifications_to_verify", "suggested_interview_topics", mode="before",
    )
    @classmethod
    def _lists(cls, v):
        return _short_list(v if isinstance(v, list) else [])

    @field_validator("match_score", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return v


@dataclass
class GenerationInput:
    """What the model may see when writing assessment questions. No name, contact details, DOB or address."""

    job_title: str
    job_description: str
    required_skills: list[str]
    preferred_skills: list[str]
    required_qualifications: str | None
    candidate_skills: list[str]
    candidate_projects: list[dict]  # [{"title": ..., "description": ...}]
    candidate_experience_years: float | None
    resume_text: str
    difficulty: str  # easy | medium | hard
    count: int
    avoid_texts: list[str] = field(default_factory=list)  # existing questions, to avoid duplicates
    focus_skill: str | None = None  # used when regenerating a single question


class GeneratedMCQ(BaseModel):
    """One AI-written multiple choice question. Validated strictly; invalid items are dropped, never repaired."""

    text: str = Field(min_length=10, max_length=1000)
    options: list[str]
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(default="", max_length=1000)
    difficulty: Literal["easy", "medium", "hard"]
    topic: str = Field(default="General", max_length=100)
    skill: str = Field(default="", max_length=100)
    q_type: Literal["technical", "concept", "resume", "project", "problem_solving", "situational"] = "technical"

    @field_validator("options", mode="before")
    @classmethod
    def _opts(cls, v):
        if not isinstance(v, list):
            raise ValueError("options must be a list")
        return [str(x).strip()[:300] for x in v]

    @model_validator(mode="after")
    def _check(self):
        if len(self.options) != 4 or any(not o for o in self.options) or len({o.lower() for o in self.options}) != 4:
            raise ValueError("exactly four distinct, non-empty options are required")
        return self


class GeneratedSentence(BaseModel):
    text: str = Field(min_length=20, max_length=250)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    @model_validator(mode="after")
    def _words(self):
        if not 5 <= len(self.text.split()) <= 30:
            raise ValueError("sentence must be 5-30 words")
        return self


class AIProviderError(Exception):
    """Provider unavailable, misconfigured or returned unusable output. Message is safe to show to staff."""


class AIProvider:
    name = "base"
    model = ""
    is_mock = False

    def analyze_resume(self, data: AnalysisInput) -> ResumeAnalysisResult:  # pragma: no cover - interface
        raise NotImplementedError

    def generate_mcq(self, data: GenerationInput) -> list[GeneratedMCQ]:  # pragma: no cover - interface
        raise NotImplementedError

    def generate_sentences(self, data: GenerationInput) -> list[GeneratedSentence]:  # pragma: no cover - interface
        raise NotImplementedError
