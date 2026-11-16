"""Heuristic extraction of facts from resume text (bulk screening).

These are best-effort guesses, not ground truth. Every result carries `warnings` for fields that could not be
found, and reviewers must check the resume itself. No AI is involved here, so this is deterministic and free.
"""

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{4,5}(?!\d)")
YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:professional\s+|total\s+|work\s+)?experience", re.I)
YEARS_RE2 = re.compile(r"experience\s*(?:of|:)?\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.I)

# Common engineering / IT skills. Opening skills are added at runtime so each opening is matched on its own terms.
BUILTIN_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "sql", "postgresql", "mysql", "mongodb",
    "react", "angular", "vue", "node.js", "django", "flask", "fastapi", "spring", "docker", "kubernetes", "aws", "azure",
    "gcp", "git", "linux", "html", "css", "rest", "graphql", "machine learning", "deep learning", "pandas", "numpy",
    "tensorflow", "pytorch", "excel", "power bi", "tableau", "autocad", "solidworks", "catia", "ansys", "matlab",
    "plc", "scada", "embedded c", "iot", "cad", "fea", "cfd", "gd&t", "six sigma", "lean", "project management",
    "communication", "leadership", "testing", "selenium", "jenkins", "ci/cd",
]

DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\.?|m\.?\s?tech|m\.?\s?e\.?|b\.?\s?sc|m\.?\s?sc|b\.?\s?c\.?a|m\.?\s?c\.?a|mba|ph\.?d|diploma|"
    r"bachelor(?:'s)?(?: of [a-z ]{3,30})?|master(?:'s)?(?: of [a-z ]{3,30})?)\b",
    re.I,
)
NAME_STOP = re.compile(r"resume|curriculum|vitae|cv|profile|contact|email|phone|address|objective|summary", re.I)


@dataclass
class Extracted:
    candidate_name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = field(default_factory=list)
    experience_years: float | None = None
    education: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _guess_name(text: str) -> str | None:
    for line in text.splitlines()[:12]:
        line = line.strip()
        if not line or len(line) > 50 or NAME_STOP.search(line) or "@" in line or re.search(r"\d", line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z.'\-]+", w) for w in words):
            return " ".join(w.capitalize() if w.isupper() else w for w in words)
    return None


def _guess_phone(text: str) -> str | None:
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 10 <= len(digits) <= 13:
            return m.group().strip()
    return None


ACRONYMS = {"aws", "gcp", "sql", "html", "css", "rest", "iot", "cad", "fea", "cfd", "plc", "scada", "gd&t", "ci/cd", "c++", "c#", "cv"}
SPECIAL = {"postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB", "javascript": "JavaScript", "typescript": "TypeScript",
           "fastapi": "FastAPI", "graphql": "GraphQL", "node.js": "Node.js", "power bi": "Power BI", "pytorch": "PyTorch",
           "tensorflow": "TensorFlow", "autocad": "AutoCAD", "solidworks": "SolidWorks", "catia": "CATIA", "ansys": "ANSYS"}


def _display(term: str, from_opening: bool) -> str:
    if from_opening:
        return term
    low = term.lower()
    if low in SPECIAL:
        return SPECIAL[low]
    if low in ACRONYMS:
        return low.upper() if low not in ("c++", "c#") else low.upper()
    return low.title()


def _find_skills(text: str, vocabulary: list[str], n_opening: int = 0) -> list[str]:
    low = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for i, term in enumerate(vocabulary):
        t = term.strip()
        if not t or t.lower() in seen:
            continue
        pattern = r"(?<![A-Za-z0-9+#])" + re.escape(t.lower()) + r"(?![A-Za-z0-9+#])"
        if re.search(pattern, low):
            seen.add(t.lower())
            found.append(_display(t, i < n_opening))
    return found[:40]


def extract(text: str, extra_skills: list[str] | None = None) -> Extracted:
    out = Extracted()
    text = text or ""
    m = EMAIL_RE.search(text)
    out.email = m.group().lower() if m else None
    out.phone = _guess_phone(text)
    out.candidate_name = _guess_name(text)
    extra = [x for x in (extra_skills or []) if isinstance(x, str)]
    out.skills = _find_skills(text, extra + BUILTIN_SKILLS, len(extra))

    years = None
    for rx in (YEARS_RE, YEARS_RE2):
        mm = rx.search(text)
        if mm:
            years = float(mm.group(1))
            break
    out.experience_years = years if years is not None and years <= 50 else None

    edu: list[str] = []
    for line in text.splitlines():
        if DEGREE_RE.search(line) and len(line.strip()) <= 160:
            cleaned = re.sub(r"\s+", " ", line.strip())
            if cleaned not in edu:
                edu.append(cleaned)
        if len(edu) >= 4:
            break
    out.education = edu

    if not out.candidate_name:
        out.warnings.append("Name not found; check the resume.")
    if not out.email:
        out.warnings.append("No email found, so duplicates cannot be detected by email.")
    if not out.phone:
        out.warnings.append("No phone number found.")
    if out.experience_years is None:
        out.warnings.append("Years of experience were not stated explicitly.")
    if not out.skills:
        out.warnings.append("No known skills were recognised.")
    if len(text.strip()) < 200:
        out.warnings.append("Very little text was extracted; the file may be a scan or image.")
    return out
