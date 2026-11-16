"""Evaluation, review and release (Phase 6).

Rules enforced here:
* Objective answers are scored from the pinned immutable snapshot with the verified keys. No negative marking.
* Repeat the Sentence is transcribed by a speech provider and compared with the expected sentence. A transcript that is
  empty, failed or low-confidence is FLAGGED and left unscored until a person listens and confirms or overrides it.
  The mock speech provider cannot understand audio, so with it every real recording is flagged by design.
* Every manual change records reviewer, time, original score, revised score and reason.
* The applicant sees nothing until a reviewer finalises AND releases. Release shows scores and optional feedback only,
  never answer keys, internal comments or other candidates.
* No score, and nothing here, ever rejects anyone automatically. Decisions are separate, human, and explained.
"""

import logging

from fastapi import BackgroundTasks, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    Assessment,
    AssessmentSchedule,
    AssessmentVersion,
    ApplicationStatus,
    AttemptAnswer,
    AttemptRecording,
    AttemptStatus,
    CandidateProfile,
    EvaluationComment,
    EvaluationItem,
    EvaluationResult,
    EvaluationStatus,
    JobApplication,
    JobOpening,
    RecordingTranscript,
    Role,
    ScheduleEvent,
    ScoreOverride,
    SttStatus,
    TestAttempt,
    User,
)
from app.models.base import utcnow
from app.schemas.evaluation import (
    CommentOut, EvaluationDetail, EvaluationListItem, ItemGroup, ItemOut, MyResult, MySection, OverrideOut,
    RecordingRef, SectionScore, SpeechView,
)
from app.services import access, application_service, audit_service, email_service, notification_service, speech_scoring, storage_service
from app.speech import SpeechProviderError, get_speech_provider, speech_status

log = logging.getLogger("hireai.evaluation")
S = ApplicationStatus
MCQ_KINDS = ("mcq", "aptitude")


# ---- helpers -------------------------------------------------------------------------------------

def _snapshot(db: Session, sch: AssessmentSchedule) -> dict:
    v = db.get(AssessmentVersion, sch.version_id)
    assert v is not None
    return v.snapshot


def _items(db: Session, ev: EvaluationResult) -> list[EvaluationItem]:
    return list(db.scalars(select(EvaluationItem).where(EvaluationItem.evaluation_id == ev.id).order_by(EvaluationItem.id)).all())


def _qmap(snap: dict) -> dict[int, dict]:
    return {q["question_id"]: q for s in snap["sections"] for q in s["questions"]}


def _titles(snap: dict) -> dict[str, str]:
    return {s["kind"]: s["title"] for s in snap["sections"]}


def _r(x: float) -> float:
    return round(float(x), 2)


def _unresolved(items: list[EvaluationItem]) -> int:
    return sum(1 for i in items if i.final_marks is None)


def _section_scores(snap: dict, items: list[EvaluationItem]) -> list[SectionScore]:
    out = []
    for s in snap["sections"]:
        its = [i for i in items if i.section == s["kind"]]
        obj = s["kind"] in MCQ_KINDS
        out.append(SectionScore(
            kind=s["kind"], title=s["title"], obtained=_r(sum(i.final_marks or 0 for i in its)), total=_r(sum(i.max_marks for i in its)),
            correct=sum(1 for i in its if obj and i.is_correct), incorrect=sum(1 for i in its if obj and not i.unanswered and i.is_correct is False),
            unanswered=sum(1 for i in its if i.unanswered), unresolved=_unresolved(its),
        ))
    return out


def _summary(ev: EvaluationResult, sections: list[SectionScore], duration: int) -> str:
    unresolved = sum(s.unresolved for s in sections)
    parts = [f"Scored {ev.total_obtained:g} of {ev.total_marks:g} marks" + (f" ({ev.percentage:.1f}%)." if ev.percentage is not None else ".")]
    parts.append(" ".join(f"{s.title}: {s.obtained:g}/{s.total:g}." for s in sections))
    if ev.time_taken_seconds is not None:
        parts.append(f"Time used: {ev.time_taken_seconds // 60} of {duration} minutes.")
    if unresolved:
        parts.append(f"{unresolved} item(s) are not scored yet and need a reviewer (speech could not be scored with enough confidence); the total is incomplete.")
    parts.append("Automatic summary from fixed rules, not written by AI. It is one input for people to weigh, not a decision.")
    return " ".join(parts)


def recompute(db: Session, ev: EvaluationResult) -> None:
    sch = db.get(AssessmentSchedule, ev.schedule_id)
    assert sch is not None
    snap = _snapshot(db, sch)
    items = _items(db, ev)
    ev.total_marks = _r(sum(i.max_marks for i in items))
    ev.total_obtained = _r(sum(i.final_marks or 0 for i in items))
    ev.percentage = round(ev.total_obtained / ev.total_marks * 100, 1) if ev.total_marks else None
    ev.summary = _summary(ev, _section_scores(snap, items), sch.duration_minutes)
    db.flush()


# ---- creation (objective scoring) -------------------------------------------------------------------

def get_for_attempt(db: Session, attempt_id: int) -> EvaluationResult | None:
    return db.scalar(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id))


def evaluate_attempt(db: Session, att: TestAttempt, sch: AssessmentSchedule) -> EvaluationResult:
    """Idempotent. Flushes only; the caller commits. No external calls happen here."""
    existing = get_for_attempt(db, att.id)
    if existing:
        return existing
    snap = _snapshot(db, sch)
    answers = {a.question_id: a for a in db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == att.id)).all()}
    finals = {r.question_id: r for r in db.scalars(select(AttemptRecording).where(AttemptRecording.attempt_id == att.id, AttemptRecording.is_final.is_(True))).all()}
    had_client_problem = bool(db.scalar(select(func.count()).select_from(ScheduleEvent).where(
        ScheduleEvent.attempt_id == att.id, ScheduleEvent.kind.in_(("client_mic_denied", "client_recording_failed")))))
    taken = int(((att.submitted_at or utcnow()) - att.started_at).total_seconds())
    ev = EvaluationResult(attempt_id=att.id, schedule_id=sch.id, application_id=sch.application_id, time_taken_seconds=max(0, min(taken, sch.duration_minutes * 60 + 60)),
                          speech_is_mock=speech_status()["is_mock"], speech_provider=speech_status()["provider"])
    db.add(ev)
    db.flush()
    for s in snap["sections"]:
        for q in s["questions"]:
            base = dict(evaluation_id=ev.id, question_id=q["question_id"], section=s["kind"], position=q["position"], max_marks=q["marks"])
            if s["kind"] in MCQ_KINDS:
                a = answers.get(q["question_id"])
                sel = a.selected_index if a else None
                ok = None if sel is None else sel == q["correct_index"]
                marks = float(q["marks"]) if ok else 0.0
                db.add(EvaluationItem(**base, selected_index=sel, is_correct=ok, unanswered=sel is None, auto_marks=marks, final_marks=marks))
            elif q["question_id"] in finals:
                db.add(EvaluationItem(**base, stt_status=SttStatus.PENDING, needs_review=True, review_note="Speech has not been processed yet."))
            else:
                note = "No recording was saved." + (" The browser reported a microphone or recording problem, so please check before treating this as zero." if had_client_problem else "")
                db.add(EvaluationItem(**base, unanswered=True, stt_status=SttStatus.NO_RECORDING, auto_marks=0.0, final_marks=0.0, needs_review=had_client_problem, review_note=note))
    db.flush()
    recompute(db, ev)
    audit_service.log_action(db, "evaluation.created", actor=None, entity_type="evaluation_result", entity_id=ev.id, details={"attempt_id": att.id})
    return ev


# ---- speech processing ------------------------------------------------------------------------------

def _apply_transcript(item: EvaluationItem, q: dict, text: str, confidence: float | None, provider) -> None:
    cmp = speech_scoring.compare(q["text"], text) if text else {}
    item.details = {"speech": {"expected": q["text"], "recognized": text, "confidence": confidence, "provider": provider.name, "is_mock": provider.is_mock, "error": None,
                               "accuracy": cmp.get("accuracy"), "completeness": cmp.get("completeness"), "missing": cmp.get("missing", []), "substituted": cmp.get("substituted", []),
                               "near_matches": cmp.get("near_matches", []), "extra": cmp.get("extra", []), "order_differs": cmp.get("order_differs", False)}}
    if not text:
        item.stt_status, item.needs_review, item.auto_marks, item.final_marks = SttStatus.LOW_CONFIDENCE, True, None, None
        item.review_note = "No speech could be recognised (silence, a poor recording, or the mock speech provider that cannot read audio). Please listen to the recording and score it."
        return
    item.auto_marks = _r(item.max_marks * (cmp["accuracy"] or 0))
    if confidence is None or confidence < get_settings().stt_min_confidence:
        item.stt_status, item.needs_review, item.final_marks = SttStatus.LOW_CONFIDENCE, True, None
        item.review_note = "Low-confidence transcript: the suggested score is provisional. Please listen to the recording, then confirm or change it."
    else:
        item.stt_status, item.needs_review, item.final_marks, item.review_note = SttStatus.OK, False, item.auto_marks, None


def process_speech(db: Session, evaluation_id: int) -> int:
    ev = db.get(EvaluationResult, evaluation_id)
    if ev is None or ev.status == EvaluationStatus.FINAL:
        return 0
    sch = db.get(AssessmentSchedule, ev.schedule_id)
    assert sch is not None
    qmap = _qmap(_snapshot(db, sch))
    pending = [i for i in _items(db, ev) if i.stt_status == SttStatus.PENDING and not i.overridden]
    if not pending:
        return 0
    try:
        provider = get_speech_provider()
    except SpeechProviderError as exc:
        for i in pending:
            i.stt_status, i.needs_review, i.review_note = SttStatus.FAILED, True, f"Speech-to-text is unavailable: {exc} Please listen and score manually."
        recompute(db, ev)
        db.commit()
        return 0
    done = 0
    for item in pending:
        rec = db.scalar(select(AttemptRecording).where(AttemptRecording.attempt_id == ev.attempt_id, AttemptRecording.question_id == item.question_id, AttemptRecording.is_final.is_(True)))
        if rec is None:
            continue
        tr = db.scalar(select(RecordingTranscript).where(RecordingTranscript.recording_id == rec.id))
        try:
            if tr is None:
                data = storage_service.path_for(rec.stored_name).read_bytes()
                t = provider.transcribe(data, rec.mime)
                tr = RecordingTranscript(recording_id=rec.id, provider=provider.name, model=provider.model, is_mock=provider.is_mock, text=t.text, confidence=t.confidence)
                db.add(tr)
            _apply_transcript(item, qmap[item.question_id], tr.text, tr.confidence, provider)
            done += 1
        except (SpeechProviderError, OSError, ValueError) as exc:
            log.warning("speech processing failed for item %s: %s", item.id, exc)
            item.stt_status, item.needs_review, item.final_marks, item.auto_marks = SttStatus.FAILED, True, None, None
            item.review_note = "Speech-to-text failed for this recording. Please listen and score it manually."
            item.details = {"speech": {"expected": qmap[item.question_id]["text"], "recognized": "", "confidence": None, "provider": provider.name, "is_mock": provider.is_mock, "error": str(exc)[:200],
                                       "accuracy": None, "completeness": None, "missing": [], "substituted": [], "near_matches": [], "extra": [], "order_differs": False}}
        db.flush()
    ev.speech_provider, ev.speech_is_mock = provider.name, provider.is_mock
    recompute(db, ev)
    db.commit()
    return done


def process_speech_for_attempt(attempt_id: int) -> None:
    """Background task entry point (opens its own session)."""
    from app.database import SessionLocal

    try:
        with SessionLocal() as db:
            ev = get_for_attempt(db, attempt_id)
            if ev:
                process_speech(db, ev.id)
    except Exception:  # background work must never crash the worker
        log.exception("speech processing for attempt %s failed", attempt_id)


def sweep(db: Session) -> dict:
    """Create evaluations for submitted attempts that lack one, and retry pending speech."""
    missing = db.scalars(select(TestAttempt).where(TestAttempt.status == AttemptStatus.SUBMITTED, ~select(EvaluationResult.id).where(EvaluationResult.attempt_id == TestAttempt.id).exists()).limit(50)).all()
    for att in missing:
        evaluate_attempt(db, att, db.get(AssessmentSchedule, att.schedule_id))  # type: ignore[arg-type]
    db.commit()
    ids = db.scalars(select(EvaluationItem.evaluation_id).where(EvaluationItem.stt_status == SttStatus.PENDING).distinct().limit(10)).all()
    processed = sum(process_speech(db, i) for i in ids)
    return {"evaluations_created": len(missing), "speech_processed": processed}


# ---- staff access --------------------------------------------------------------------------------------

def _require_staff(db: Session, user: User, ev: EvaluationResult) -> JobApplication:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    app = application_service.get_application(db, ev.application_id)
    access.require_opening_access(db, user, app.opening_id)
    access.require_perm(db, user, "review_results")
    return app


def staff_get(db: Session, user: User, evaluation_id: int) -> EvaluationResult:
    ev = db.get(EvaluationResult, evaluation_id)
    if ev is None:
        raise AppError(404, "not_found", "Evaluation not found.")
    _require_staff(db, user, ev)
    return ev


def ensure_for_schedule(db: Session, user: User, schedule_id: int) -> EvaluationResult:
    sch = db.get(AssessmentSchedule, schedule_id)
    if sch is None or user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    app = application_service.get_application(db, sch.application_id)
    access.require_opening_access(db, user, app.opening_id)
    access.require_perm(db, user, "review_results")
    att = db.scalar(select(TestAttempt).where(TestAttempt.schedule_id == sch.id))
    if att is None or att.status != AttemptStatus.SUBMITTED:
        raise AppError(409, "not_submitted", "The applicant has not submitted this test yet.")
    ev = evaluate_attempt(db, att, sch)
    db.commit()
    return ev


def list_evaluations(db: Session, user: User, *, status: str | None, released: bool | None, needs_review: bool | None, search: str | None, page: int, page_size: int):
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    access.require_perm(db, user, "review_results")
    q = (select(EvaluationResult, JobApplication, JobOpening, User)
         .join(JobApplication, JobApplication.id == EvaluationResult.application_id)
         .join(JobOpening, JobOpening.id == JobApplication.opening_id)
         .join(CandidateProfile, CandidateProfile.id == JobApplication.candidate_id)
         .join(User, User.id == CandidateProfile.user_id))
    scope = access.staff_scope(db, user)
    if scope is not None:
        q = q.where(JobApplication.opening_id.in_(scope))
    if status:
        q = q.where(EvaluationResult.status == EvaluationStatus(status))
    if released is not None:
        q = q.where(EvaluationResult.released_at.is_not(None) if released else EvaluationResult.released_at.is_(None))
    if needs_review:
        q = q.where(select(EvaluationItem.id).where(EvaluationItem.evaluation_id == EvaluationResult.id, EvaluationItem.final_marks.is_(None)).exists())
    if search:
        like = f"%{search.strip()}%"
        q = q.where(User.full_name.ilike(like) | JobOpening.title.ilike(like))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(EvaluationResult.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return [_list_item(db, *r) for r in rows], total


def _list_item(db: Session, ev: EvaluationResult, app: JobApplication, opening: JobOpening, cand: User) -> EvaluationListItem:
    att = db.get(TestAttempt, ev.attempt_id)
    return EvaluationListItem(
        id=ev.id, application_id=app.id, schedule_id=ev.schedule_id, candidate_name=cand.full_name, opening_title=opening.title, test_date=att.submitted_at if att else None,
        status=ev.status, total_marks=ev.total_marks, total_obtained=ev.total_obtained, percentage=ev.percentage, unresolved=_unresolved(_items(db, ev)),
        released=ev.released_at is not None, application_status=app.status.value,
    )


def blockers(db: Session, ev: EvaluationResult) -> list[str]:
    n = _unresolved(_items(db, ev))
    return [f"{n} speaking item(s) still need a score: listen to the recording, then confirm the suggestion or enter a score."] if n else []


def detail(db: Session, user: User, ev: EvaluationResult) -> EvaluationDetail:
    app = application_service.get_application(db, ev.application_id)
    opening = db.get(JobOpening, app.opening_id)
    cand = application_service.applicant_user(db, app)
    sch = db.get(AssessmentSchedule, ev.schedule_id)
    assessment = db.get(Assessment, sch.assessment_id)  # type: ignore[union-attr]
    snap = _snapshot(db, sch)  # type: ignore[arg-type]
    qmap, titles = _qmap(snap), _titles(snap)
    items = _items(db, ev)
    recs: dict[int, list[AttemptRecording]] = {}
    for r in db.scalars(select(AttemptRecording).where(AttemptRecording.attempt_id == ev.attempt_id).order_by(AttemptRecording.attempt_no)).all():
        recs.setdefault(r.question_id, []).append(r)
    groups: dict[str, list[ItemOut]] = {}
    for i in items:
        q = qmap[i.question_id]
        opts = q.get("options") if i.section in MCQ_KINDS else None
        sp = (i.details or {}).get("speech")
        groups.setdefault(i.section, []).append(ItemOut(
            id=i.id, question_id=i.question_id, section=i.section, position=i.position, text=q["text"], options=opts, selected_index=i.selected_index,
            selected_text=opts[i.selected_index] if opts and i.selected_index is not None else None, correct_index=q.get("correct_index") if opts else None,
            correct_text=opts[q["correct_index"]] if opts else None, is_correct=i.is_correct, unanswered=i.unanswered, max_marks=i.max_marks, auto_marks=i.auto_marks,
            final_marks=i.final_marks, overridden=i.overridden, needs_review=i.needs_review, review_note=i.review_note, stt_status=i.stt_status,
            speech=SpeechView(**sp) if sp else None, recordings=[RecordingRef(id=r.id, attempt_no=r.attempt_no, is_final=r.is_final) for r in recs.get(i.question_id, [])],
        ))
    pos = {i.id: i for i in items}
    overrides = [OverrideOut(id=o.id, item_id=o.item_id, question_position=pos[o.item_id].position, section=pos[o.item_id].section, original_marks=o.original_marks,
                             revised_marks=o.revised_marks, reason=o.reason, changed_by=(db.get(User, o.changed_by).full_name if o.changed_by else None), changed_at=o.changed_at)
                 for o in db.scalars(select(ScoreOverride).where(ScoreOverride.evaluation_id == ev.id).order_by(ScoreOverride.id.desc())).all() if o.item_id in pos]
    comments = [CommentOut(id=c.id, author=(db.get(User, c.author_id).full_name if c.author_id else None), body=c.body, created_at=c.created_at)
                for c in db.scalars(select(EvaluationComment).where(EvaluationComment.evaluation_id == ev.id).order_by(EvaluationComment.id.desc())).all()]
    base = _list_item(db, ev, app, opening, cand)  # type: ignore[arg-type]
    return EvaluationDetail(
        **base.model_dump(), candidate_email=cand.email, assessment_title=assessment.title if assessment else "", assessment_is_mock=bool(assessment.is_mock) if assessment else False,
        duration_minutes=sch.duration_minutes, time_taken_seconds=ev.time_taken_seconds, summary=ev.summary,  # type: ignore[union-attr]
        sections=_section_scores(snap, items), groups=[ItemGroup(kind=k, title=titles.get(k, k), items=v) for k, v in groups.items()],
        overrides=overrides, comments=comments, blockers=blockers(db, ev), can_edit=ev.status == EvaluationStatus.DRAFT,
        speech_provider=ev.speech_provider, speech_is_mock=ev.speech_is_mock, applicant_feedback=ev.applicant_feedback, finalized_at=ev.finalized_at, released_at=ev.released_at,
    )


# ---- review actions ----------------------------------------------------------------------------------------

def _need_draft(ev: EvaluationResult) -> None:
    if ev.status != EvaluationStatus.DRAFT:
        raise AppError(409, "evaluation_final", "This evaluation is final. Reopen it (if it has not been released) to change scores.")


def _item(db: Session, ev: EvaluationResult, item_id: int) -> EvaluationItem:
    it = db.get(EvaluationItem, item_id)
    if it is None or it.evaluation_id != ev.id:
        raise AppError(404, "not_found", "Item not found.")
    return it


def override_item(db: Session, user: User, ev: EvaluationResult, item_id: int, marks: float, reason: str, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    _need_draft(ev)
    it = _item(db, ev, item_id)
    if marks > it.max_marks:
        raise AppError(422, "marks_too_high", f"The maximum for this question is {it.max_marks:g}.", fields={"marks": f"At most {it.max_marks:g}"})
    db.add(ScoreOverride(evaluation_id=ev.id, item_id=it.id, original_marks=it.final_marks if it.final_marks is not None else it.auto_marks, revised_marks=_r(marks), reason=reason.strip(), changed_by=user.id))
    it.final_marks, it.overridden, it.needs_review = _r(marks), True, False
    it.review_note = f"Score set by {user.full_name}."
    if it.stt_status in (SttStatus.PENDING, SttStatus.FAILED):
        it.stt_status = SttStatus.LOW_CONFIDENCE if it.details else it.stt_status
    recompute(db, ev)
    audit_service.log_action(db, "evaluation.score_overridden", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request, details={"item_id": it.id, "revised": _r(marks), "reason": reason})
    db.commit()
    return ev


def confirm_item(db: Session, user: User, ev: EvaluationResult, item_id: int, note: str | None, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    _need_draft(ev)
    it = _item(db, ev, item_id)
    if it.final_marks is not None or it.auto_marks is None:
        raise AppError(409, "nothing_to_confirm", "This item has no provisional score to confirm. Enter a score instead.")
    it.final_marks, it.needs_review, it.review_note = it.auto_marks, False, f"Provisional score confirmed by {user.full_name} after review." + (f" {note}" if note else "")
    recompute(db, ev)
    audit_service.log_action(db, "evaluation.score_confirmed", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request, details={"item_id": it.id})
    db.commit()
    return ev


def add_comment(db: Session, user: User, ev: EvaluationResult, body: str, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    db.add(EvaluationComment(evaluation_id=ev.id, author_id=user.id, body=body.strip()))
    audit_service.log_action(db, "evaluation.comment_added", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request)
    db.commit()
    return ev


def rerun_speech(db: Session, user: User, ev: EvaluationResult, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    _need_draft(ev)
    redo = 0
    for it in _items(db, ev):
        if it.stt_status in (SttStatus.FAILED, SttStatus.LOW_CONFIDENCE, SttStatus.PENDING) and not it.overridden and it.stt_status != SttStatus.NO_RECORDING:
            rec = db.scalar(select(AttemptRecording).where(AttemptRecording.attempt_id == ev.attempt_id, AttemptRecording.question_id == it.question_id, AttemptRecording.is_final.is_(True)))
            if rec is None:
                continue
            for tr in db.scalars(select(RecordingTranscript).where(RecordingTranscript.recording_id == rec.id)).all():
                db.delete(tr)
            it.stt_status, it.needs_review, it.final_marks, it.auto_marks, it.details = SttStatus.PENDING, True, None, None, None
            redo += 1
    db.flush()
    audit_service.log_action(db, "evaluation.speech_rerun", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request, details={"items": redo})
    db.commit()
    process_speech(db, ev.id)
    return ev


def finalize(db: Session, user: User, ev: EvaluationResult, request: Request) -> EvaluationResult:
    app = _require_staff(db, user, ev)
    _need_draft(ev)
    b = blockers(db, ev)
    if b:
        raise AppError(409, "unresolved_items", b[0])
    ev.status, ev.finalized_by, ev.finalized_at = EvaluationStatus.FINAL, user.id, utcnow()
    recompute(db, ev)
    application_service._record(db, app, app.status, user, f"Assessment evaluation approved ({ev.total_obtained:g}/{ev.total_marks:g}).", visible=False, comment_only=True)
    audit_service.log_action(db, "evaluation.finalized", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request)
    db.commit()
    return ev


def reopen(db: Session, user: User, ev: EvaluationResult, reason: str, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    if ev.status != EvaluationStatus.FINAL:
        raise AppError(409, "not_final", "This evaluation is not final.")
    if ev.released_at is not None:
        raise AppError(409, "already_released", "Withdraw the release before reopening this evaluation.")
    ev.status, ev.finalized_by, ev.finalized_at = EvaluationStatus.DRAFT, None, None
    db.add(EvaluationComment(evaluation_id=ev.id, author_id=user.id, body=f"Reopened for changes: {reason}"))
    audit_service.log_action(db, "evaluation.reopened", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request, details={"reason": reason})
    db.commit()
    return ev


def release(db: Session, user: User, ev: EvaluationResult, feedback: str | None, request: Request, background: BackgroundTasks | None) -> EvaluationResult:
    app = _require_staff(db, user, ev)
    if ev.status != EvaluationStatus.FINAL:
        raise AppError(409, "not_final", "Approve the evaluation before releasing it to the applicant.")
    if ev.released_at is not None:
        raise AppError(409, "already_released", "This result has already been released.")
    ev.released_at, ev.released_by, ev.applicant_feedback = utcnow(), user.id, (feedback or "").strip() or None
    cand = application_service.applicant_user(db, app)
    title = app.opening.title
    notification_service.notify(db, cand.id, "result_released", "Your assessment result is available", f"Your result for “{title}” is now available.", f"/my-results/{ev.id}")
    email_service.queue_email(db, background, to_email=cand.email, subject=f"Your assessment result for {title}", template="result_released", title="Your assessment result is ready",
                              paragraphs=[f"Hello {cand.full_name},", f"Your result for the online assessment for “{title}” is now available in your account.",
                                          "It is one input into the hiring process; decisions are made by people at SolidPro."],
                              button=("View your result", f"{get_settings().frontend_url.rstrip('/')}/my-results/{ev.id}"), user_id=cand.id)
    audit_service.log_action(db, "evaluation.released", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request)
    db.commit()
    return ev


def unrelease(db: Session, user: User, ev: EvaluationResult, reason: str, request: Request) -> EvaluationResult:
    _require_staff(db, user, ev)
    if ev.released_at is None:
        raise AppError(409, "not_released", "This result has not been released.")
    ev.released_at, ev.released_by = None, None
    db.add(EvaluationComment(evaluation_id=ev.id, author_id=user.id, body=f"Release withdrawn: {reason}"))
    audit_service.log_action(db, "evaluation.release_withdrawn", actor=user, entity_type="evaluation_result", entity_id=ev.id, request=request, details={"reason": reason})
    db.commit()
    return ev


# ---- final decisions (human only) ------------------------------------------------------------------------------

def decide(db: Session, user: User, application_id: int, decision: str, reason: str | None, request: Request, background: BackgroundTasks | None) -> JobApplication:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    app = application_service.get_application(db, application_id)
    access.require_opening_access(db, user, app.opening_id)
    access.require_perm(db, user, "review_results")
    final_eval = db.scalar(select(EvaluationResult).where(EvaluationResult.application_id == app.id, EvaluationResult.status == EvaluationStatus.FINAL))
    if decision == "shortlist":
        if app.status != S.APPROVED:
            raise AppError(409, "invalid_state", "Only an approved application can be shortlisted.")
        if final_eval is None:
            raise AppError(409, "evaluation_required", "Approve the assessment evaluation before shortlisting.")
        to, headline, body = S.SHORTLISTED, "You have been shortlisted", "Good news: you have been shortlisted for the next stage."
    elif decision == "select":
        if app.status != S.SHORTLISTED:
            raise AppError(409, "invalid_state", "Only a shortlisted candidate can be selected.")
        to, headline, body = S.SELECTED, "You have been selected", "Congratulations: you have been selected. The team will contact you about the next steps."
    else:
        if app.status not in (S.APPROVED, S.SHORTLISTED):
            raise AppError(409, "invalid_state", "Only an application at the assessment or shortlist stage can be rejected here.")
        to, headline, body = S.REJECTED, "Update on your application", "Thank you for your interest. After careful review, we will not be moving forward with your application."
    application_service._record(db, app, to, user, reason, visible=True)
    app.decided_by, app.decided_at, app.decision_reason = user.id, utcnow(), reason
    cand = application_service.applicant_user(db, app)
    title = app.opening.title
    notification_service.notify(db, cand.id, f"application_{to.value}", headline, f"{body} (“{title}”)", f"/my-applications/{app.id}")
    paragraphs = [f"Hello {cand.full_name},", f"{body} Position: “{title}”."]
    if reason:
        paragraphs.append(f"Message from the recruitment team: {reason}")
    email_service.queue_email(db, background, to_email=cand.email, subject=f"Update on your application for {title}", template=f"application_{to.value}", title=headline, paragraphs=paragraphs,
                              button=("View application", f"{get_settings().frontend_url.rstrip('/')}/my-applications/{app.id}"), user_id=cand.id)
    audit_service.log_action(db, f"application.{to.value}", actor=user, entity_type="job_application", entity_id=app.id, request=request, details={"reason": reason, "evaluation_id": final_eval.id if final_eval else None})
    db.commit()
    return app


# ---- applicant view -------------------------------------------------------------------------------------------------

def _my_result(db: Session, ev: EvaluationResult) -> MyResult:
    app = application_service.get_application(db, ev.application_id)
    sch = db.get(AssessmentSchedule, ev.schedule_id)
    assessment = db.get(Assessment, sch.assessment_id)  # type: ignore[union-attr]
    att = db.get(TestAttempt, ev.attempt_id)
    sections = [MySection(kind=s.kind, title=s.title, obtained=s.obtained, total=s.total) for s in _section_scores(_snapshot(db, sch), _items(db, ev))]  # type: ignore[arg-type]
    return MyResult(id=ev.id, application_id=app.id, opening_title=app.opening.title, assessment_title=assessment.title if assessment else "", test_date=att.submitted_at if att else None,
                    released_at=ev.released_at, total_marks=ev.total_marks, total_obtained=ev.total_obtained, percentage=ev.percentage, sections=sections,  # type: ignore[arg-type]
                    time_taken_seconds=ev.time_taken_seconds, feedback=ev.applicant_feedback)


def my_results(db: Session, user: User) -> list[MyResult]:
    cp = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id)) if user.role == Role.APPLICANT else None
    if cp is None:
        raise AppError(404, "not_found", "Not found.")
    rows = db.scalars(select(EvaluationResult).join(JobApplication, JobApplication.id == EvaluationResult.application_id)
                      .where(JobApplication.candidate_id == cp.id, EvaluationResult.released_at.is_not(None), EvaluationResult.status == EvaluationStatus.FINAL)
                      .order_by(EvaluationResult.released_at.desc())).all()
    return [_my_result(db, e) for e in rows]


def my_result(db: Session, user: User, evaluation_id: int) -> MyResult:
    for r in my_results(db, user):
        if r.id == evaluation_id:
            return r
    raise AppError(404, "not_found", "Result not found.")  # unreleased results do not exist as far as the applicant can tell
