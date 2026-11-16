"""Deterministic, offline "analysis" used for development, demos and tests.

It only matches keywords and compares numbers. It does NOT understand the resume, and every report it
produces is labelled MOCK in the API and the UI so nobody mistakes it for real AI output.
"""

import re

from app.ai.mock_content import ALIASES, MCQ_POOL, SENTENCES
from app.ai.schemas import (
    AIProvider,
    AnalysisInput,
    GeneratedMCQ,
    GeneratedSentence,
    GenerationInput,
    ResumeAnalysisResult,
)

PLACEHOLDER = "[MOCK PLACEHOLDER]"
_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def _norm(t: str) -> str:
    return " ".join(t.lower().split())


def _pool_key(skill: str) -> str | None:
    k = skill.strip().lower()
    k = ALIASES.get(k, k)
    return k if k in MCQ_POOL else None


def _has(term: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term.strip())}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def _years_needed(text: str | None) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


class MockProvider(AIProvider):
    name = "mock"
    model = "keyword-matcher-v1"
    is_mock = True

    def analyze_resume(self, data: AnalysisInput) -> ResumeAnalysisResult:
        haystack = data.resume_text + "\n" + "\n".join(data.candidate_skills)
        matched = [s for s in data.required_skills if _has(s, haystack)]
        missing = [s for s in data.required_skills if s not in matched]
        pref = [s for s in data.preferred_skills if _has(s, haystack)]

        req_cov = len(matched) / len(data.required_skills) if data.required_skills else 0.5
        pref_cov = len(pref) / len(data.preferred_skills) if data.preferred_skills else req_cov

        need = _years_needed(data.required_experience)
        have = data.candidate_experience_years
        if need and have is not None:
            exp_cov = min(1.0, have / need)
            exp_text = f"Profile states {have:g} year(s); the opening asks for about {need:g}."
        else:
            exp_cov = 0.5
            exp_text = "Experience could not be compared (not stated on the opening or the profile)."

        has_edu = bool(data.candidate_education)
        edu_text = (
            "Education: " + "; ".join(f"{e.get('degree', '')} {e.get('department') or ''}".strip() for e in data.candidate_education[:3])
            if has_edu else "No education entries on the profile."
        )
        score = round(100 * (0.6 * req_cov + 0.1 * pref_cov + 0.2 * exp_cov + 0.1 * (1.0 if has_edu else 0.0)))

        strengths = [f"Resume mentions required skill: {s}" for s in matched[:6]]
        strengths += [f"Resume mentions preferred skill: {s}" for s in pref[:3]]
        gaps = [f"Required skill not found in the resume text: {s}" for s in missing[:8]]
        return ResumeAnalysisResult(
            match_score=score,
            confidence="low",
            summary=(
                f"[MOCK] Keyword match only: {len(matched)} of {len(data.required_skills)} required skills found. "
                "This is not an AI assessment. A person must review the resume."
            ),
            matched_required_skills=matched,
            missing_required_skills=missing,
            matched_preferred_skills=pref,
            experience_assessment=exp_text,
            education_assessment=edu_text,
            strengths=strengths,
            gaps=gaps,
            clarifications_to_verify=["Keyword matching cannot judge depth or recency of skills. Verify in the interview."],
            suggested_interview_topics=[f"Ask for a concrete example using {s}" for s in matched[:4]]
            + [f"Probe familiarity with {s}" for s in missing[:3]],
        )

    # ------------------------------------------------------------ assessment generation

    def generate_mcq(self, data: GenerationInput) -> list[GeneratedMCQ]:
        """Curated questions for recognised skills, then placeholders that a reviewer must rewrite."""
        skills = [data.focus_skill] if data.focus_skill else list(data.required_skills) + list(data.candidate_skills) + list(data.preferred_skills)
        seen_keys: list[str] = []
        for sk in skills:
            key = _pool_key(sk)
            if key and key not in seen_keys:
                seen_keys.append(key)
        avoid = {_norm(t) for t in data.avoid_texts}
        target = _ORDER.get(data.difficulty, 1)
        candidates: list[tuple[str, tuple]] = []
        for key in seen_keys:
            for item in sorted(MCQ_POOL[key], key=lambda it: abs(_ORDER[it[4]] - target)):
                if _norm(item[0]) not in avoid:
                    candidates.append((key, item))
        out: list[GeneratedMCQ] = []
        # round-robin across skills so one skill does not take every slot
        by_skill: dict[str, list[tuple]] = {}
        for key, item in candidates:
            by_skill.setdefault(key, []).append(item)
        while len(out) < data.count and any(by_skill.values()):
            for key in list(by_skill):
                if by_skill[key] and len(out) < data.count:
                    text, options, ci, expl, diff, topic = by_skill[key].pop(0)
                    out.append(GeneratedMCQ(text=text, options=options, correct_index=ci, explanation=expl, difficulty=diff, topic=topic, skill=key, q_type="technical"))
        n = 0
        pool_skills = [s for s in (data.required_skills or ["the role"]) if s]
        while len(out) < data.count:
            skill = data.focus_skill or pool_skills[n % len(pool_skills)]
            n += 1
            out.append(GeneratedMCQ(
                text=f"{PLACEHOLDER} Write a {data.difficulty} multiple choice question about {skill} for the {data.job_title} role.",
                options=["Option A (replace)", "Option B (replace)", "Option C (replace)", "Option D (replace)"], correct_index=0,
                explanation="Replace this placeholder with a real explanation.", difficulty=data.difficulty if data.difficulty in _ORDER else "medium",
                topic="Needs authoring", skill=skill, q_type="technical",
            ))
        return out

    def generate_sentences(self, data: GenerationInput) -> list[GeneratedSentence]:
        avoid = {_norm(t) for t in data.avoid_texts}
        target = _ORDER.get(data.difficulty, 1)
        pool = [(t, d) for t, d in sorted(SENTENCES, key=lambda it: abs(_ORDER[it[1]] - target)) if _norm(t) not in avoid]
        return [GeneratedSentence(text=t, difficulty=d) for t, d in pool[: data.count]]
