"""Assessment generation, human review and approval.

Rules enforced here (spec section 10-11):
* Exactly three sections: MCQ, Aptitude, Repeat the Sentence. No coding section.
* AI writes MCQ and Repeat-the-Sentence items only. Aptitude items come from the reusable bank, never from the resume.
* Nothing is usable until a person approves every question and then approves the whole assessment, which creates an
  immutable, hash-stamped version. Any later edit reopens the draft and needs a fresh approval; older versions stay intact.
* Questions are copies. Editing the bank afterwards never changes an assessment or an approved version.
"""

import hashlib
import json
import random

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.factory import get_provider
from app.ai.mock_provider import PLACEHOLDER
from app.ai.schemas import GENERATION_PROMPT_VERSION, AIProvider, AIProviderError, GeneratedMCQ, GenerationInput
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    Assessment,
    AssessmentApproval,
    AssessmentQuestion,
    AssessmentSection,
    AssessmentStatus,
    AssessmentVersion,
    BankQuestion,
    CandidateEducation,  # noqa: F401  (kept for parity with analysis input building)
    CandidateExperience,
    CandidateProfile,
    CandidateSkill,
    Difficulty,
    JobApplication,
    QuestionBank,
    QuestionSource,
    QuestionStatus,
    SectionKind,
    User,
)
from app.models.base import utcnow
from app.models.recruitment import ApplicationStatus, ExperienceKind
from app.schemas.assessment import (
    AIInfo,
    ApprovalOut,
    AssessmentConfig,
    AssessmentDetail,
    AssessmentListItem,
    AssessmentUpdate,
    GenerateRequest,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    SectionOut,
    VersionDetail,
    VersionOut,
)
from app.services import access, application_service, audit_service

SECTION_TITLES = {SectionKind.MCQ: "MCQ", SectionKind.APTITUDE: "Aptitude", SectionKind.REPEAT_SENTENCE: "Repeat the Sentence"}
SECTION_ORDER = [SectionKind.MCQ, SectionKind.APTITUDE, SectionKind.REPEAT_SENTENCE]
NOTICE = (
    "Questions are drafts until a person approves them. Applicants cannot see any question or answer; only an approved, "
    "published version can ever be used for a test."
)
_DIFF = {"easy": 0, "medium": 1, "hard": 2}


# ------------------------------------------------------------------ access


def _need(db: Session, user: User, *codes: str) -> None:
    if not any(access.has_permission(db, user, c) for c in codes):
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")


def get_assessment(db: Session, assessment_id: int) -> Assessment:
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise AppError(404, "not_found", "Assessment not found.")
    return a


def _app(db: Session, a: Assessment) -> JobApplication:
    return application_service.get_application(db, a.application_id)


def require_view(db: Session, user: User, a: Assessment) -> JobApplication:
    _need(db, user, "generate_assessments", "approve_assessments")
    app = _app(db, a)
    access.require_opening_access(db, user, app.opening_id)
    return app


def require_edit(db: Session, user: User, a: Assessment) -> JobApplication:
    _need(db, user, "approve_assessments")
    app = _app(db, a)
    access.require_opening_access(db, user, app.opening_id)
    return app


def require_generate(db: Session, user: User, a: Assessment) -> JobApplication:
    _need(db, user, "generate_assessments")
    app = _app(db, a)
    access.require_opening_access(db, user, app.opening_id)
    return app


# ------------------------------------------------------------------ helpers


def _sections(db: Session, a: Assessment) -> list[AssessmentSection]:
    return list(db.scalars(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id).order_by(AssessmentSection.position)).all())


def _questions(db: Session, a: Assessment) -> list[AssessmentQuestion]:
    return list(db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == a.id).order_by(AssessmentQuestion.position, AssessmentQuestion.id)).all())


def _section_for(db: Session, a: Assessment, kind: SectionKind) -> AssessmentSection:
    return db.scalars(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id, AssessmentSection.kind == kind)).one()


def _next_position(db: Session, section: AssessmentSection) -> int:
    return (db.scalar(select(func.max(AssessmentQuestion.position)).where(AssessmentQuestion.section_id == section.id)) or 0) + 1


def _is_placeholder(q: AssessmentQuestion) -> bool:
    return q.text.startswith(PLACEHOLDER)


def _versions(db: Session, a: Assessment) -> list[AssessmentVersion]:
    return list(db.scalars(select(AssessmentVersion).where(AssessmentVersion.assessment_id == a.id).order_by(AssessmentVersion.version.desc())).all())


def _canon(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(snapshot: dict) -> str:
    return hashlib.sha256(_canon(snapshot).encode()).hexdigest()


def build_snapshot(db: Session, a: Assessment) -> dict:
    """The exact content a version will freeze. Approved questions only; answer keys included (staff-side record)."""
    qs = [q for q in _questions(db, a) if q.status == QuestionStatus.APPROVED]
    sections = []
    for s in _sections(db, a):
        items = [q for q in qs if q.section_id == s.id]
        sections.append({
            "kind": s.kind.value, "title": s.title, "total_marks": sum(q.marks for q in items),
            "questions": [
                {"question_id": q.id, "position": i + 1, "text": q.text, "options": q.options, "correct_index": q.correct_index,
                 "explanation": q.explanation, "difficulty": q.difficulty.value, "topic": q.topic, "skill": q.skill,
                 "marks": q.marks, "source": q.source.value, "bank_question_id": q.bank_question_id}
                for i, q in enumerate(items)
            ],
        })
    cfg = a.config or {}
    return {
        "assessment_id": a.id, "title": a.title, "difficulty": a.difficulty.value, "duration_minutes": a.duration_minutes,
        "repeat_sentence_settings": {k: cfg.get(k) for k in ("rs_max_replays", "rs_max_attempts", "rs_record_seconds")},
        "generated_with": {"provider": a.provider, "model": a.model, "is_mock": a.is_mock, "prompt_version": a.prompt_version},
        "sections": sections, "total_marks": sum(s["total_marks"] for s in sections),
    }


def blockers_for(db: Session, a: Assessment) -> list[str]:
    qs = _questions(db, a)
    live = [q for q in qs if q.status != QuestionStatus.REJECTED]
    out: list[str] = []
    for s in _sections(db, a):
        if not any(q.section_id == s.id for q in live):
            out.append(f"The {s.title} section has no questions.")
    pending = sum(1 for q in live if q.status == QuestionStatus.PENDING)
    if pending:
        out.append(f"{pending} question(s) still need to be approved or rejected.")
    ph = sum(1 for q in live if _is_placeholder(q))
    if ph:
        out.append(f"{ph} placeholder question(s) must be rewritten or deleted.")
    return out


def _touch(a: Assessment) -> None:
    """Any content change reopens the draft; an approved version already created is never modified."""
    a.status = AssessmentStatus.DRAFT


def _log(db: Session, user: User, request: Request, action: str, a: Assessment, **details) -> None:
    audit_service.log_action(db, action, actor=user, entity_type="assessment", entity_id=a.id, request=request, details=details or None)


# ------------------------------------------------------------------ output


def _q_out(db: Session, q: AssessmentQuestion) -> QuestionOut:
    rev = db.get(User, q.reviewed_by) if q.reviewed_by else None
    return QuestionOut(
        id=q.id, section=q.kind, position=q.position, status=q.status, source=q.source, text=q.text, options=q.options,
        correct_index=q.correct_index, explanation=q.explanation, difficulty=q.difficulty, topic=q.topic, skill=q.skill,
        q_type=q.q_type, marks=q.marks, edited=q.edited, is_placeholder=_is_placeholder(q),
        reviewed_by_name=rev.full_name if rev else None, reviewed_at=q.reviewed_at, reject_reason=q.reject_reason,
    )


def _names(db: Session, app: JobApplication) -> tuple[str, str]:
    return application_service.applicant_user(db, app).full_name, app.opening.title


def detail(db: Session, user: User, a: Assessment) -> AssessmentDetail:
    app = _app(db, a)
    cand, opening = _names(db, app)
    qs = _questions(db, a)
    sections = []
    for s in _sections(db, a):
        items = [q for q in qs if q.section_id == s.id]
        sections.append(SectionOut(id=s.id, kind=s.kind, title=s.title, total_marks=sum(q.marks for q in items if q.status != QuestionStatus.REJECTED),
                                   questions=[_q_out(db, q) for q in items]))
    versions = _versions(db, a)
    ver_out = []
    for v in versions:
        ap = db.get(User, v.approved_by) if v.approved_by else None
        pb = db.get(User, v.published_by) if v.published_by else None
        ver_out.append(VersionOut(id=v.id, version=v.version, total_marks=v.total_marks, duration_minutes=v.duration_minutes, content_hash=v.content_hash,
                                  approved_by_name=ap.full_name if ap else None, approved_at=v.approved_at, published_at=v.published_at,
                                  published_by_name=pb.full_name if pb else None))
    ver_no = {v.id: v.version for v in versions}
    approvals = []
    for ap_row in db.scalars(select(AssessmentApproval).where(AssessmentApproval.assessment_id == a.id).order_by(AssessmentApproval.id.desc())).all():
        rv = db.get(User, ap_row.reviewer_id) if ap_row.reviewer_id else None
        approvals.append(ApprovalOut(id=ap_row.id, version=ver_no.get(ap_row.version_id, 0), reviewer_name=rv.full_name if rv else None, decision=ap_row.decision,
                                     note=ap_row.note, question_ids=ap_row.question_ids, changes=ap_row.changes, created_at=ap_row.created_at))
    live = [q for q in qs if q.status != QuestionStatus.REJECTED]
    creator = db.get(User, a.created_by) if a.created_by else None
    published = [v.version for v in versions if v.published_at]
    return AssessmentDetail(
        id=a.id, application_id=a.application_id, candidate_name=cand, opening_title=opening, title=a.title, status=a.status, difficulty=a.difficulty,
        duration_minutes=a.duration_minutes, config=AssessmentConfig.model_validate(a.config),
        ai=AIInfo(provider=a.provider, model=a.model, is_mock=a.is_mock, prompt_version=a.prompt_version),
        created_by_name=creator.full_name if creator else None, created_at=a.created_at, updated_at=a.updated_at, sections=sections,
        total_marks=sum(q.marks for q in live),
        counts={"total": len(qs), "approved": sum(q.status == QuestionStatus.APPROVED for q in qs), "pending": sum(q.status == QuestionStatus.PENDING for q in qs),
                "rejected": sum(q.status == QuestionStatus.REJECTED for q in qs)},
        blockers=blockers_for(db, a), has_unapproved_changes=bool(versions) and a.status == AssessmentStatus.DRAFT,
        latest_version=versions[0].version if versions else None, published_version=max(published) if published else None,
        versions=ver_out, approvals=approvals, generation_notes=list(a.generation_notes or []),
        can_edit=access.has_permission(db, user, "approve_assessments"), can_generate=access.has_permission(db, user, "generate_assessments"), notice=NOTICE,
    )


def list_assessments(db: Session, user: User, *, status=None, opening_id=None, application_id=None, search=None, page=1, page_size=15):
    _need(db, user, "generate_assessments", "approve_assessments")
    q = select(Assessment).join(JobApplication, JobApplication.id == Assessment.application_id)
    scope = access.staff_scope(db, user)
    if scope is not None:
        q = q.where(JobApplication.opening_id.in_(scope or [-1]))
    if opening_id:
        q = q.where(JobApplication.opening_id == opening_id)
    if application_id:
        q = q.where(Assessment.application_id == application_id)
    if status:
        q = q.where(Assessment.status == AssessmentStatus(status))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(Assessment.title.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Assessment.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    items = []
    for a in rows:
        app = _app(db, a)
        cand, opening = _names(db, app)
        qs = [x for x in _questions(db, a) if x.status != QuestionStatus.REJECTED]
        vs = _versions(db, a)
        pub = [v.version for v in vs if v.published_at]
        items.append(AssessmentListItem(
            id=a.id, application_id=a.application_id, candidate_name=cand, opening_title=opening, title=a.title, status=a.status, is_mock=a.is_mock,
            total_marks=sum(x.marks for x in qs), question_count=len(qs), pending_count=sum(x.status == QuestionStatus.PENDING for x in qs),
            latest_version=vs[0].version if vs else None, published_version=max(pub) if pub else None, created_at=a.created_at,
        ))
    return items, total


# ------------------------------------------------------------------ generation


def _generation_input(db: Session, app: JobApplication, *, difficulty: str, count: int, avoid: list[str], focus: str | None = None) -> GenerationInput:
    cp = db.get(CandidateProfile, app.candidate_id)
    skills = [s.name for s in db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == cp.id)).all()]
    projects = [
        {"title": e.title, "description": (e.description or "")[:500]}
        for e in db.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == cp.id, CandidateExperience.kind.in_([ExperienceKind.PROJECT, ExperienceKind.INTERNSHIP]))).all()
    ][:6]
    o = app.opening
    return GenerationInput(
        job_title=o.title, job_description=o.description, required_skills=list(o.required_skills or []), preferred_skills=list(o.preferred_skills or []),
        required_qualifications=o.required_qualifications, candidate_skills=skills, candidate_projects=projects,
        candidate_experience_years=float(cp.total_experience_years) if cp.total_experience_years is not None else None,
        resume_text=(app.resume.extracted_text or "")[: get_settings().ai_max_resume_chars], difficulty=difficulty, count=count, avoid_texts=avoid, focus_skill=focus,
    )


def _relevant(skill: str, allowed: list[str]) -> bool:
    s = skill.strip().lower()
    if not s or s in ("general", "n/a", "none"):
        return True
    return any(s in a or a in s for a in allowed if a)


def _shuffle(options: list[str], correct: int, seed: str) -> tuple[list[str], int]:
    order = list(range(len(options)))
    random.Random(seed).shuffle(order)
    return [options[i] for i in order], order.index(correct)


def _provider() -> AIProvider:
    try:
        return get_provider()
    except AIProviderError as e:
        raise AppError(503, "ai_unavailable", str(e)) from e


def _pick_bank(db: Session, opening_category_id: int, topics: list[str], exclude_ids: set[int], count: int, difficulty: str, seed: str) -> list[BankQuestion]:
    rows = db.scalars(
        select(BankQuestion).join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
        .where(BankQuestion.is_active.is_(True), QuestionBank.is_active.is_(True), BankQuestion.topic.in_(topics),
               or_(QuestionBank.category_id.is_(None), QuestionBank.category_id == opening_category_id), BankQuestion.id.not_in(exclude_ids or {-1}))
        .order_by(BankQuestion.id)
    ).all()
    rng = random.Random(seed)
    by_topic: dict[str, list[BankQuestion]] = {}
    for r in rows:
        by_topic.setdefault(r.topic, []).append(r)
    for lst in by_topic.values():
        rng.shuffle(lst)
        lst.sort(key=lambda x: abs(_DIFF[x.difficulty.value] - _DIFF[difficulty]))  # stable: prefers the requested difficulty
    picked: list[BankQuestion] = []
    while len(picked) < count and any(by_topic.values()):
        for t in [t for t in topics if by_topic.get(t)]:
            if len(picked) < count:
                picked.append(by_topic[t].pop(0))
    return picked


def generate(db: Session, user: User, req: GenerateRequest, request: Request) -> Assessment:
    _need(db, user, "generate_assessments")
    app = application_service.get_application(db, req.application_id)
    access.require_opening_access(db, user, app.opening_id)
    if app.status != ApplicationStatus.APPROVED:
        raise AppError(409, "application_not_approved", "An assessment can only be created for an application that was approved for assessment.")
    if db.scalar(select(Assessment.id).where(Assessment.application_id == app.id)):
        raise AppError(409, "assessment_exists", "This application already has an assessment. Open it to continue.")
    cfg, diff = req.config, req.difficulty.value
    provider = _provider()
    notes: list[str] = []
    gi = _generation_input(db, app, difficulty=diff, count=cfg.mcq_count, avoid=[])
    allowed = [s.lower() for s in gi.required_skills + gi.preferred_skills + gi.candidate_skills]
    try:
        raw_mcq = provider.generate_mcq(gi)
        raw_rs = provider.generate_sentences(GenerationInput(**{**gi.__dict__, "count": cfg.rs_count}))
    except AIProviderError as e:
        raise AppError(502, "ai_failed", str(e)) from e
    mcqs = [m for m in raw_mcq if _relevant(m.skill, allowed)]
    if len(raw_mcq) - len(mcqs):
        notes.append(f"{len(raw_mcq) - len(mcqs)} generated question(s) were dropped because they were about skills unrelated to this role.")
    mcqs = mcqs[: cfg.mcq_count]
    if len(mcqs) < cfg.mcq_count:
        notes.append(f"Only {len(mcqs)} of {cfg.mcq_count} MCQ questions could be generated. Regenerate or add questions manually.")
    sentences = raw_rs[: cfg.rs_count]
    if len(sentences) < cfg.rs_count:
        notes.append(f"Only {len(sentences)} of {cfg.rs_count} Repeat the Sentence items could be generated.")
    a = Assessment(
        application_id=app.id, title=(req.title or f"{app.opening.title} assessment").strip(), status=AssessmentStatus.DRAFT, difficulty=req.difficulty,
        duration_minutes=req.duration_minutes, config=cfg.model_dump(), provider=provider.name, model=provider.model, prompt_version=GENERATION_PROMPT_VERSION,
        is_mock=provider.is_mock, created_by=user.id,
    )
    db.add(a)
    db.flush()
    secs = {k: AssessmentSection(assessment_id=a.id, kind=k, position=i + 1, title=SECTION_TITLES[k]) for i, k in enumerate(SECTION_ORDER)}
    db.add_all(secs.values())
    db.flush()
    source = QuestionSource.TEMPLATE if provider.is_mock else QuestionSource.AI
    for i, m in enumerate(mcqs):
        opts, ci = _shuffle(m.options, m.correct_index, f"{a.id}:mcq:{i}")
        db.add(AssessmentQuestion(assessment_id=a.id, section_id=secs[SectionKind.MCQ].id, kind=SectionKind.MCQ, position=i + 1, source=source, text=m.text,
                                  options=opts, correct_index=ci, explanation=m.explanation or None, difficulty=Difficulty(m.difficulty), topic=m.topic,
                                  skill=m.skill or None, q_type=m.q_type, marks=cfg.mcq_marks))
    picks = _pick_bank(db, app.opening.category_id, list(cfg.aptitude_topics), set(), cfg.aptitude_count, diff, f"{a.id}:apt")
    if len(picks) < cfg.aptitude_count:
        notes.append(f"The aptitude bank only had {len(picks)} suitable question(s) for the {cfg.aptitude_count} requested. Add questions to the bank or the assessment.")
    for i, b in enumerate(picks):
        db.add(AssessmentQuestion(assessment_id=a.id, section_id=secs[SectionKind.APTITUDE].id, kind=SectionKind.APTITUDE, position=i + 1, source=QuestionSource.BANK,
                                  bank_question_id=b.id, text=b.text, options=list(b.options), correct_index=b.correct_index, explanation=b.explanation,
                                  difficulty=b.difficulty, topic=b.topic, marks=cfg.aptitude_marks))
    for i, s in enumerate(sentences):
        db.add(AssessmentQuestion(assessment_id=a.id, section_id=secs[SectionKind.REPEAT_SENTENCE].id, kind=SectionKind.REPEAT_SENTENCE, position=i + 1, source=source,
                                  text=s.text, difficulty=Difficulty(s.difficulty), topic="Repeat the sentence", marks=cfg.rs_marks))
    a.generation_notes = notes
    if provider.is_mock:
        notes.insert(0, "MOCK mode: questions come from a small curated pool or are placeholders. Set AI_PROVIDER=anthropic for job- and resume-specific questions.")
    _log(db, user, request, "assessment.generated", a, application_id=app.id, provider=provider.name, mock=provider.is_mock,
         counts={"mcq": len(mcqs), "aptitude": len(picks), "repeat_sentence": len(sentences)})
    db.commit()
    return a


# ------------------------------------------------------------------ editing


def update_assessment(db: Session, user: User, a: Assessment, data: AssessmentUpdate, request: Request) -> Assessment:
    require_edit(db, user, a)
    patch = data.model_dump(exclude_unset=True, exclude_none=True)
    if "config" in patch:
        a.config = data.config.model_dump()
    for f in ("title", "difficulty", "duration_minutes"):
        if f in patch:
            setattr(a, f, patch[f])
    _touch(a)
    _log(db, user, request, "assessment.updated", a, fields=sorted(patch))
    db.commit()
    return a


def _get_q(db: Session, a: Assessment, qid: int) -> AssessmentQuestion:
    q = db.get(AssessmentQuestion, qid)
    if q is None or q.assessment_id != a.id:
        raise AppError(404, "not_found", "Question not found.")
    return q


def _validate_final(q: AssessmentQuestion) -> None:
    errs: dict[str, str] = {}
    if q.kind == SectionKind.REPEAT_SENTENCE:
        if not 5 <= len(q.text.split()) <= 30:
            errs["text"] = "The sentence should be 5 to 30 words"
    else:
        opts = q.options or []
        if not 2 <= len(opts) <= 6 or any(not o for o in opts) or len({o.lower() for o in opts}) != len(opts):
            errs["options"] = "Provide 2 to 6 different, non-empty options"
        elif q.correct_index is None or not 0 <= q.correct_index < len(opts):
            errs["correct_index"] = "Mark one of the options as correct"
    if errs:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields=errs)


def update_question(db: Session, user: User, a: Assessment, qid: int, data: QuestionUpdate, request: Request) -> AssessmentQuestion:
    require_edit(db, user, a)
    q = _get_q(db, a, qid)
    patch = data.model_dump(exclude_unset=True)
    if q.kind == SectionKind.REPEAT_SENTENCE and (patch.get("options") or patch.get("correct_index") is not None):
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"options": "Repeat the Sentence items have no options"})
    for k, v in patch.items():
        if k in ("options", "correct_index", "explanation", "topic", "skill") or v is not None:
            setattr(q, k, v.strip() if isinstance(v, str) and k == "text" else v)
    _validate_final(q)
    q.edited = True
    q.status, q.reviewed_by, q.reviewed_at, q.reject_reason = QuestionStatus.PENDING, None, None, None  # an edited question must be re-approved
    _touch(a)
    _log(db, user, request, "assessment.question_edited", a, question_id=q.id, fields=sorted(patch))
    db.commit()
    return q


def add_question(db: Session, user: User, a: Assessment, data: QuestionCreate, request: Request) -> AssessmentQuestion:
    require_edit(db, user, a)
    sec = _section_for(db, a, data.section)
    q = AssessmentQuestion(assessment_id=a.id, section_id=sec.id, kind=data.section, position=_next_position(db, sec), source=QuestionSource.MANUAL, text=data.text.strip(),
                           options=data.options, correct_index=data.correct_index, explanation=data.explanation, difficulty=data.difficulty,
                           topic=data.topic, skill=data.skill, marks=data.marks, edited=False)
    _validate_final(q)
    db.add(q)
    _touch(a)
    db.flush()
    _log(db, user, request, "assessment.question_added", a, question_id=q.id, section=data.section.value, source="manual")
    db.commit()
    return q


def add_from_bank(db: Session, user: User, a: Assessment, bank_question_id: int, request: Request) -> AssessmentQuestion:
    require_edit(db, user, a)
    b = db.get(BankQuestion, bank_question_id)
    if b is None or not b.is_active:
        raise AppError(404, "not_found", "Bank question not found.")
    if db.scalar(select(AssessmentQuestion.id).where(AssessmentQuestion.assessment_id == a.id, AssessmentQuestion.bank_question_id == b.id,
                                                      AssessmentQuestion.status != QuestionStatus.REJECTED)):
        raise AppError(409, "duplicate", "This question is already in the assessment.")
    sec = _section_for(db, a, SectionKind.APTITUDE)
    q = AssessmentQuestion(assessment_id=a.id, section_id=sec.id, kind=SectionKind.APTITUDE, position=_next_position(db, sec), source=QuestionSource.BANK,
                           bank_question_id=b.id, text=b.text, options=list(b.options), correct_index=b.correct_index, explanation=b.explanation,
                           difficulty=b.difficulty, topic=b.topic, marks=(a.config or {}).get("aptitude_marks", b.marks))
    db.add(q)
    _touch(a)
    db.flush()
    _log(db, user, request, "assessment.question_added", a, question_id=q.id, section="aptitude", source="bank", bank_question_id=b.id)
    db.commit()
    return q


def approve_question(db: Session, user: User, a: Assessment, qid: int, request: Request) -> AssessmentQuestion:
    require_edit(db, user, a)
    q = _get_q(db, a, qid)
    if _is_placeholder(q):
        raise AppError(409, "placeholder", "This is a placeholder. Rewrite it before approving.")
    q.status, q.reviewed_by, q.reviewed_at, q.reject_reason = QuestionStatus.APPROVED, user.id, utcnow(), None
    _touch(a)
    _log(db, user, request, "assessment.question_approved", a, question_id=q.id)
    db.commit()
    return q


def approve_all_questions(db: Session, user: User, a: Assessment, request: Request) -> int:
    """Convenience for a reviewer who has read the whole list. Placeholders are skipped, never approved."""
    require_edit(db, user, a)
    n = 0
    for q in _questions(db, a):
        if q.status == QuestionStatus.PENDING and not _is_placeholder(q):
            q.status, q.reviewed_by, q.reviewed_at = QuestionStatus.APPROVED, user.id, utcnow()
            n += 1
    if n:
        _touch(a)
    _log(db, user, request, "assessment.questions_approved_bulk", a, count=n)
    db.commit()
    return n


def reject_question(db: Session, user: User, a: Assessment, qid: int, reason: str | None, request: Request) -> AssessmentQuestion:
    require_edit(db, user, a)
    q = _get_q(db, a, qid)
    q.status, q.reviewed_by, q.reviewed_at, q.reject_reason = QuestionStatus.REJECTED, user.id, utcnow(), (reason or "").strip() or None
    _touch(a)
    _log(db, user, request, "assessment.question_rejected", a, question_id=q.id)
    db.commit()
    return q


def delete_question(db: Session, user: User, a: Assessment, qid: int, request: Request) -> None:
    require_edit(db, user, a)
    q = _get_q(db, a, qid)
    section_id = q.section_id
    db.delete(q)
    db.flush()
    for i, r in enumerate(db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.section_id == section_id).order_by(AssessmentQuestion.position, AssessmentQuestion.id)).all()):
        r.position = i + 1
    _touch(a)
    _log(db, user, request, "assessment.question_deleted", a, question_id=qid)
    db.commit()


def regenerate_question(db: Session, user: User, a: Assessment, qid: int, request: Request) -> AssessmentQuestion:
    require_generate(db, user, a)
    _need(db, user, "approve_assessments")
    app = _app(db, a)
    q = _get_q(db, a, qid)
    avoid = [x.text for x in _questions(db, a)]
    diff = q.difficulty.value
    if q.kind == SectionKind.APTITUDE:
        used = {x.bank_question_id for x in _questions(db, a) if x.bank_question_id and x.status != QuestionStatus.REJECTED}
        topics = [q.topic] if q.topic else list((a.config or {}).get("aptitude_topics", []))
        pick = (_pick_bank(db, app.opening.category_id, topics, used, 1, diff, f"{a.id}:{q.id}:{utcnow().timestamp()}")
                or _pick_bank(db, app.opening.category_id, list((a.config or {}).get("aptitude_topics", [])), used, 1, diff, f"{a.id}:{q.id}:any"))
        if not pick:
            raise AppError(409, "no_replacement", "The aptitude bank has no other suitable question. Add more to the bank first.")
        b = pick[0]
        q.text, q.options, q.correct_index, q.explanation, q.difficulty, q.topic = b.text, list(b.options), b.correct_index, b.explanation, b.difficulty, b.topic
        q.bank_question_id, q.source = b.id, QuestionSource.BANK
    else:
        provider = _provider()
        gi = _generation_input(db, app, difficulty=diff, count=1, avoid=avoid, focus=q.skill if q.kind == SectionKind.MCQ else None)
        try:
            if q.kind == SectionKind.MCQ:
                allowed = [s.lower() for s in gi.required_skills + gi.preferred_skills + gi.candidate_skills]
                new: list[GeneratedMCQ] = [m for m in provider.generate_mcq(gi) if _relevant(m.skill, allowed)]
            else:
                new = provider.generate_sentences(gi)
        except AIProviderError as e:
            raise AppError(502, "ai_failed", str(e)) from e
        if not new:
            raise AppError(409, "no_replacement", "No usable replacement was generated. Try again or write one manually.")
        n = new[0]
        q.text, q.difficulty = n.text, Difficulty(n.difficulty)
        if q.kind == SectionKind.MCQ:
            q.options, q.correct_index = _shuffle(n.options, n.correct_index, f"{a.id}:{q.id}:{utcnow().timestamp()}")
            q.explanation, q.topic, q.skill, q.q_type = n.explanation or None, n.topic, n.skill or None, n.q_type
        q.source = QuestionSource.TEMPLATE if provider.is_mock else QuestionSource.AI
    q.edited = False
    q.status, q.reviewed_by, q.reviewed_at, q.reject_reason = QuestionStatus.PENDING, None, None, None
    _touch(a)
    _log(db, user, request, "assessment.question_regenerated", a, question_id=q.id)
    db.commit()
    return q


def delete_assessment(db: Session, user: User, a: Assessment, request: Request) -> None:
    require_edit(db, user, a)
    if _versions(db, a):
        raise AppError(409, "has_versions", "An assessment with an approved version cannot be deleted.")
    _log(db, user, request, "assessment.deleted", a)
    for model in (AssessmentQuestion, AssessmentSection):
        for row in db.scalars(select(model).where(model.assessment_id == a.id)).all():
            db.delete(row)
    db.flush()
    db.delete(a)
    db.commit()


# ------------------------------------------------------------------ approval and versions


def _diff(prev: dict | None, cur: dict) -> dict:
    def flat(s: dict | None) -> dict[int, dict]:
        return {q["question_id"]: q for sec in (s or {}).get("sections", []) for q in sec["questions"]}

    p, c = flat(prev), flat(cur)
    keys = ("text", "options", "correct_index", "explanation", "difficulty", "marks")
    return {
        "first_version": prev is None,
        "added": sorted(set(c) - set(p)), "removed": sorted(set(p) - set(c)),
        "edited": sorted(i for i in set(p) & set(c) if any(p[i][k] != c[i][k] for k in keys)),
    }


def approve_assessment(db: Session, user: User, a: Assessment, note: str | None, request: Request) -> AssessmentVersion:
    require_edit(db, user, a)
    problems = blockers_for(db, a)
    if problems:
        raise AppError(409, "not_ready", "The assessment is not ready for approval: " + " ".join(problems))
    snap = build_snapshot(db, a)
    digest = _hash(snap)
    versions = _versions(db, a)
    if versions and versions[0].content_hash == digest:
        raise AppError(409, "nothing_to_approve", "There are no changes since the last approved version.")
    prev = versions[0].snapshot if versions else None
    v = AssessmentVersion(assessment_id=a.id, version=(versions[0].version + 1) if versions else 1, snapshot=snap, content_hash=digest,
                          total_marks=snap["total_marks"], duration_minutes=a.duration_minutes, approved_by=user.id)
    db.add(v)
    db.flush()
    ids = [q["question_id"] for s in snap["sections"] for q in s["questions"]]
    db.add(AssessmentApproval(assessment_id=a.id, version_id=v.id, reviewer_id=user.id, decision="approved", note=(note or "").strip() or None, question_ids=ids, changes=_diff(prev, snap)))
    a.status = AssessmentStatus.APPROVED
    _log(db, user, request, "assessment.approved", a, version=v.version, hash=digest, questions=len(ids), total_marks=v.total_marks)
    db.commit()
    return v


def get_version(db: Session, user: User, a: Assessment, version: int) -> AssessmentVersion:
    require_view(db, user, a)
    v = db.scalars(select(AssessmentVersion).where(AssessmentVersion.assessment_id == a.id, AssessmentVersion.version == version)).first()
    if v is None:
        raise AppError(404, "not_found", "Version not found.")
    return v


def version_detail(db: Session, user: User, a: Assessment, version: int) -> VersionDetail:
    v = get_version(db, user, a, version)
    ap = db.get(User, v.approved_by) if v.approved_by else None
    return VersionDetail(version=v.version, content_hash=v.content_hash, integrity_ok=_hash(v.snapshot) == v.content_hash, total_marks=v.total_marks,
                         duration_minutes=v.duration_minutes, approved_by_name=ap.full_name if ap else None, approved_at=v.approved_at,
                         published_at=v.published_at, snapshot=v.snapshot)


def publish_version(db: Session, user: User, a: Assessment, version: int, request: Request) -> AssessmentVersion:
    require_edit(db, user, a)
    versions = _versions(db, a)
    v = next((x for x in versions if x.version == version), None)
    if v is None:
        raise AppError(404, "not_found", "Version not found.")
    if v.version != versions[0].version:
        raise AppError(409, "superseded", "A newer approved version exists. Publish that one instead.")
    if _hash(v.snapshot) != v.content_hash:
        raise AppError(409, "integrity_failed", "This version failed its integrity check and cannot be published.")
    if v.published_at is None:
        v.published_at, v.published_by = utcnow(), user.id  # the only columns the immutability trigger allows to change
    _log(db, user, request, "assessment.published", a, version=v.version)
    db.commit()
    return v
