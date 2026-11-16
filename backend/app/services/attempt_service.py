"""Online test taking (Phase 5).

Server-side rules (the browser is never trusted):
* The deadline lives on the server. Late saves / uploads are refused after a short grace period.
* Answer keys never leave the server. Options are sent as {id: originalIndex, text} in a per-attempt shuffled order.
* One browser session owns an attempt at a time (X-Attempt-Session). Opening it elsewhere takes it over.
* Repeat-the-Sentence: the sentence is only returned by the play endpoint, and plays are counted on the server.
* Tab-switch / copy / paste events are stored for context only. They never change the status or score.
"""

import hashlib
import random
import secrets
from datetime import timedelta

from fastapi import Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    Assessment,
    AssessmentSchedule,
    AssessmentVersion,
    AttemptAnswer,
    AttemptRecording,
    AttemptStatus,
    ScheduleEvent,
    ScheduleStatus,
    TestAttempt,
    User,
)
from app.models.base import utcnow
from app.schemas.scheduling import (
    AnswersIn,
    AnswersSaved,
    AttemptOut,
    EventsIn,
    PlayOut,
    RecordingOut,
    SubmitOut,
    TakeOption,
    TakeQuestion,
    TakeSection,
)
from app.services import application_service, audit_service, evaluation_service, notification_service, scheduling_service as sched, storage_service

MCQ_KINDS = ("mcq", "aptitude")
MAX_EVENTS_PER_ATTEMPT = 500
DEFAULT_RS = {"rs_max_replays": 1, "rs_max_attempts": 1, "rs_record_seconds": 20}


def _grace() -> timedelta:
    return timedelta(seconds=get_settings().submit_grace_seconds)


# ---- snapshot helpers ----------------------------------------------------------------------------

def _snapshot(db: Session, sch: AssessmentSchedule) -> dict:
    v = db.get(AssessmentVersion, sch.version_id)
    assert v is not None
    return v.snapshot


def _rs_settings(snap: dict) -> dict:
    cfg = {**DEFAULT_RS, **{k: v for k, v in (snap.get("repeat_sentence_settings") or {}).items() if v is not None}}
    return cfg


def _questions_by_id(snap: dict) -> dict[int, tuple[str, dict]]:
    return {q["question_id"]: (s["kind"], q) for s in snap["sections"] for q in s["questions"]}


def _build_order(snap: dict) -> dict:
    rng = random.Random(secrets.randbits(64))
    sections = []
    for s in snap["sections"]:
        qs = list(s["questions"])
        if s["kind"] in MCQ_KINDS:
            rng.shuffle(qs)  # Repeat the Sentence keeps the author's order
        items = []
        for q in qs:
            order = list(range(len(q["options"]))) if q.get("options") else []
            if s["kind"] in MCQ_KINDS:
                rng.shuffle(order)
            items.append({"question_id": q["question_id"], "option_order": order})
        sections.append({"kind": s["kind"], "questions": items})
    return {"sections": sections}


# ---- loading / guards ---------------------------------------------------------------------------

def _load(db: Session, user: User, attempt_id: int) -> tuple[TestAttempt, AssessmentSchedule]:
    att = db.get(TestAttempt, attempt_id)
    if att is None:
        raise AppError(404, "not_found", "Test not found.")
    sch = sched.get_schedule(db, att.schedule_id)
    sched.require_candidate(db, user, sch)
    return att, sch


def _finish(db: Session, att: TestAttempt, sch: AssessmentSchedule, reason: str, actor: User | None, request: Request | None = None) -> None:
    if att.status == AttemptStatus.SUBMITTED:
        return
    att.status, att.submitted_at, att.submit_reason = AttemptStatus.SUBMITTED, utcnow(), reason
    sch.status = ScheduleStatus.COMPLETED
    sched.log_event(db, sch, "submitted", actor=actor, attempt_id=att.id, details={"reason": reason})
    db.flush()
    evaluation_service.evaluate_attempt(db, att, sch)  # objective scoring now; speech is processed in the background
    audit_service.log_action(db, "attempt.submitted", actor=actor, entity_type="test_attempt", entity_id=att.id, request=request, details={"reason": reason})
    if sch.created_by:
        app = application_service.get_application(db, sch.application_id)
        cand = application_service.applicant_user(db, app)
        notification_service.notify(db, sch.created_by, "test_submitted", "Assessment submitted",
                                    f"{cand.full_name} submitted the online assessment ({'time ran out' if reason == 'timeout' else 'manual submit'}).", f"/schedules/{sch.id}")


def _writable(db: Session, att: TestAttempt, sch: AssessmentSchedule, session_id: str | None) -> None:
    """Common guard for every write during an attempt."""
    if att.status == AttemptStatus.SUBMITTED:
        raise AppError(409, "attempt_closed", "This test has already been submitted.")
    if utcnow() > att.deadline_at + _grace():
        _finish(db, att, sch, "timeout", None)
        db.commit()
        raise AppError(409, "time_up", "Time is up. Your test was submitted automatically.")
    if session_id is None or not secrets.compare_digest(session_id, att.session_id):
        raise AppError(409, "session_replaced", "This test was opened in another window or device. Reload to continue here.")


# ---- start / read --------------------------------------------------------------------------------

def start(db: Session, user: User, sch: AssessmentSchedule, consent: bool, request: Request) -> AttemptOut:
    sched.require_candidate(db, user, sch)
    if not consent:
        raise AppError(422, "consent_required", "You must agree to the recording and test conditions to start.", fields={"consent": "Consent is required."})
    sched.refresh_status(db, sch)
    now = utcnow()
    att = db.scalar(select(TestAttempt).where(TestAttempt.schedule_id == sch.id).with_for_update())
    if att is not None:
        if att.status == AttemptStatus.SUBMITTED:
            raise AppError(409, "already_submitted", "You have already submitted this test.")
        if now > att.deadline_at + _grace():
            _finish(db, att, sch, "timeout", None)
            db.commit()
            raise AppError(409, "time_up", "Time is up. Your test was submitted automatically.")
        att.session_id = secrets.token_urlsafe(24)  # resume: the newest window owns the attempt
        sched.log_event(db, sch, "attempt_resumed", actor=user, attempt_id=att.id)
        db.commit()
        return attempt_out(db, att, sch, include_session=True)
    if sch.status != ScheduleStatus.ACCEPTED:
        msg = {ScheduleStatus.INVITED: "Accept the invitation first.", ScheduleStatus.EXPIRED: "The test window has closed.",
               ScheduleStatus.CANCELLED: "This test was cancelled.", ScheduleStatus.COMPLETED: "This test is already complete."}.get(sch.status, "This test cannot be started.")
        raise AppError(409, "not_startable", msg)
    if now < sch.window_start:
        raise AppError(409, "too_early", f"The test opens at {sched._fmt(sch.window_start)}.")
    if now > sch.window_end:
        raise AppError(409, "window_closed", "The test window has closed.")
    snap = _snapshot(db, sch)
    att = TestAttempt(schedule_id=sch.id, started_at=now, deadline_at=now + timedelta(minutes=sch.duration_minutes), consented_at=now,
                      session_id=secrets.token_urlsafe(24), question_order=_build_order(snap), plays={})
    db.add(att)
    sch.status = ScheduleStatus.IN_PROGRESS
    db.flush()
    sched.log_event(db, sch, "attempt_started", actor=user, attempt_id=att.id, details={"consent": True})
    audit_service.log_action(db, "attempt.started", actor=user, entity_type="test_attempt", entity_id=att.id, request=request)
    db.commit()
    return attempt_out(db, att, sch, include_session=True)


def attempt_out(db: Session, att: TestAttempt, sch: AssessmentSchedule, *, include_session: bool = False) -> AttemptOut:
    snap = _snapshot(db, sch)
    assessment = db.get(Assessment, sch.assessment_id)
    now = utcnow()
    base = dict(id=att.id, status=att.status, assessment_title=assessment.title if assessment else snap.get("title", ""), started_at=att.started_at,
                deadline_at=att.deadline_at, server_now=now, submitted_at=att.submitted_at, session_id=att.session_id if include_session else None)
    rs = _rs_settings(snap)
    if att.status == AttemptStatus.SUBMITTED:
        return AttemptOut(**base, rs_record_seconds=rs["rs_record_seconds"], sections=[])  # nothing is re-exposed after submission
    qmap = _questions_by_id(snap)
    answers = {a.question_id: a for a in db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == att.id)).all()}
    rec_counts = dict(db.execute(select(AttemptRecording.question_id, func.count()).where(AttemptRecording.attempt_id == att.id).group_by(AttemptRecording.question_id)).all())
    titles = {s["kind"]: s["title"] for s in snap["sections"]}
    sections: list[TakeSection] = []
    for sec in att.question_order["sections"]:
        out_q: list[TakeQuestion] = []
        for i, item in enumerate(sec["questions"]):
            kind, q = qmap[item["question_id"]]
            ans = answers.get(q["question_id"])
            if kind in MCQ_KINDS:
                opts = [TakeOption(id=j, text=q["options"][j]) for j in item["option_order"]]
                out_q.append(TakeQuestion(id=q["question_id"], section=kind, position=i + 1, text=q["text"], options=opts, marks=q["marks"],
                                          selected=ans.selected_index if ans else None, marked=bool(ans and ans.marked_for_review)))
            else:
                out_q.append(TakeQuestion(id=q["question_id"], section=kind, position=i + 1, text=None, options=None, marks=q["marks"],
                                          plays_used=int((att.plays or {}).get(str(q["question_id"]), 0)), plays_allowed=1 + int(rs["rs_max_replays"]),
                                          recordings_used=int(rec_counts.get(q["question_id"], 0)), recordings_allowed=int(rs["rs_max_attempts"]),
                                          marked=bool(ans and ans.marked_for_review)))
        sections.append(TakeSection(kind=sec["kind"], title=titles.get(sec["kind"], sec["kind"]), questions=out_q))
    return AttemptOut(**base, rs_record_seconds=rs["rs_record_seconds"], sections=sections)


def get_attempt(db: Session, user: User, attempt_id: int) -> AttemptOut:
    att, sch = _load(db, user, attempt_id)
    if att.status == AttemptStatus.IN_PROGRESS and utcnow() > att.deadline_at + _grace():
        _finish(db, att, sch, "timeout", None)
        db.commit()
    return attempt_out(db, att, sch)


# ---- answers ---------------------------------------------------------------------------------------

def save_answers(db: Session, user: User, attempt_id: int, data: AnswersIn, session_id: str | None) -> AnswersSaved:
    att, sch = _load(db, user, attempt_id)
    _writable(db, att, sch, session_id)
    qmap = _questions_by_id(_snapshot(db, sch))
    saved = 0
    for item in data.answers:
        entry = qmap.get(item.question_id)
        if entry is None:
            raise AppError(422, "unknown_question", "One of the answers refers to a question that is not part of this test.")
        kind, q = entry
        if kind not in MCQ_KINDS:
            if item.selected_index is not None:
                raise AppError(422, "bad_answer", "This question is answered by speaking, not by choosing an option.")
        elif item.selected_index is not None and not 0 <= item.selected_index < len(q["options"]):
            raise AppError(422, "bad_answer", "That answer option does not exist.")
        row = db.scalar(select(AttemptAnswer).where(AttemptAnswer.attempt_id == att.id, AttemptAnswer.question_id == item.question_id).with_for_update())
        if row is None:
            db.add(AttemptAnswer(attempt_id=att.id, question_id=item.question_id, selected_index=item.selected_index, marked_for_review=item.marked_for_review, seq=item.seq))
            saved += 1
        elif item.seq >= row.seq:  # a late, out-of-order request must never overwrite a newer answer
            row.selected_index, row.marked_for_review, row.seq = item.selected_index, item.marked_for_review, item.seq
            saved += 1
    db.commit()
    return AnswersSaved(saved=saved, server_now=utcnow(), deadline_at=att.deadline_at)


# ---- repeat the sentence ---------------------------------------------------------------------------

def _rs_question(db: Session, sch: AssessmentSchedule, question_id: int) -> tuple[dict, dict]:
    snap = _snapshot(db, sch)
    entry = _questions_by_id(snap).get(question_id)
    if entry is None or entry[0] != "repeat_sentence":
        raise AppError(404, "not_found", "Question not found.")
    return entry[1], _rs_settings(snap)


def play(db: Session, user: User, attempt_id: int, question_id: int, session_id: str | None) -> PlayOut:
    att, sch = _load(db, user, attempt_id)
    _writable(db, att, sch, session_id)
    q, rs = _rs_question(db, sch, question_id)
    allowed = 1 + int(rs["rs_max_replays"])
    att = db.scalar(select(TestAttempt).where(TestAttempt.id == att.id).with_for_update())  # serialise concurrent plays
    assert att is not None
    plays = dict(att.plays or {})
    used = int(plays.get(str(question_id), 0))
    if used >= allowed:
        raise AppError(409, "no_plays_left", "You have used all plays for this sentence.")
    plays[str(question_id)] = used + 1
    att.plays = plays
    db.commit()
    return PlayOut(sentence=q["text"], plays_used=used + 1, plays_allowed=allowed,
                   mock_audio_note="The sentence is spoken by your browser's built-in speech voice. Server-generated audio is not part of this build.")


def _sniff(data: bytes) -> str | None:
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    return None


async def upload_recording(db: Session, user: User, attempt_id: int, question_id: int, file: UploadFile, duration_ms: int | None, session_id: str | None) -> RecordingOut:
    att, sch = _load(db, user, attempt_id)
    _writable(db, att, sch, session_id)
    _q, rs = _rs_question(db, sch, question_id)
    limit = get_settings().max_recording_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise AppError(422, "empty_recording", "The recording was empty. Please record again.")
    if len(data) > limit:
        raise AppError(413, "recording_too_large", f"The recording is larger than {get_settings().max_recording_mb} MB.")
    mime = _sniff(data)
    if mime is None:
        raise AppError(422, "bad_audio", "That file is not a supported audio recording (webm, ogg, mp4 or wav).")
    max_ms = int(rs["rs_record_seconds"]) * 1000 + 3000
    if duration_ms is not None and not 0 <= duration_ms <= max_ms:
        raise AppError(422, "recording_too_long", f"Recordings can be at most {rs['rs_record_seconds']} seconds.")
    att = db.scalar(select(TestAttempt).where(TestAttempt.id == att.id).with_for_update())
    assert att is not None
    if int((att.plays or {}).get(str(question_id), 0)) < 1:
        raise AppError(409, "play_first", "Listen to the sentence before recording your answer.")
    used = db.scalar(select(func.count()).select_from(AttemptRecording).where(AttemptRecording.attempt_id == att.id, AttemptRecording.question_id == question_id)) or 0
    if used >= int(rs["rs_max_attempts"]):
        raise AppError(409, "no_recordings_left", "You have used all recording attempts for this sentence.")
    for old in db.scalars(select(AttemptRecording).where(AttemptRecording.attempt_id == att.id, AttemptRecording.question_id == question_id)).all():
        old.is_final = False
    stored = storage_service.save_bytes(data)
    rec = AttemptRecording(attempt_id=att.id, question_id=question_id, attempt_no=used + 1, stored_name=stored, mime=mime, size_bytes=len(data),
                           duration_ms=duration_ms, sha256=hashlib.sha256(data).hexdigest(), is_final=True)
    db.add(rec)
    db.flush()
    sched.log_event(db, sch, "recording_saved", actor=user, attempt_id=att.id, details={"question_id": question_id, "attempt_no": rec.attempt_no})
    db.commit()
    return _rec_out(rec)


def _rec_out(r: AttemptRecording) -> RecordingOut:
    return RecordingOut(id=r.id, question_id=r.question_id, attempt_no=r.attempt_no, size_bytes=r.size_bytes, duration_ms=r.duration_ms, mime=r.mime, created_at=r.created_at)


# ---- events / submit -------------------------------------------------------------------------------

def record_events(db: Session, user: User, attempt_id: int, data: EventsIn, session_id: str | None) -> int:
    att, sch = _load(db, user, attempt_id)
    if att.status == AttemptStatus.SUBMITTED:
        return 0
    if session_id is None or not secrets.compare_digest(session_id, att.session_id):
        return 0  # a replaced session's events are not interesting
    existing = db.scalar(select(func.count()).select_from(ScheduleEvent).where(ScheduleEvent.attempt_id == att.id, ScheduleEvent.client_reported.is_(True))) or 0
    room = max(0, MAX_EVENTS_PER_ATTEMPT - existing)
    for e in data.events[:room]:
        sched.log_event(db, sch, f"client_{e.kind}", actor=user, attempt_id=att.id, client=True, details={"detail": e.detail, "client_time": e.at.isoformat() if e.at else None})
    db.commit()
    return min(room, len(data.events))


def _summary(db: Session, att: TestAttempt, sch: AssessmentSchedule) -> SubmitOut:
    s = sched.attempt_summary(db, sch)
    assert s is not None
    return SubmitOut(status=att.status, submitted_at=att.submitted_at, submit_reason=att.submit_reason, answered=s.answered, total_questions=s.total_questions)


def submit(db: Session, user: User, attempt_id: int, request: Request, session_id: str | None = None) -> SubmitOut:
    att, sch = _load(db, user, attempt_id)
    if att.status == AttemptStatus.SUBMITTED:
        return _summary(db, att, sch)  # idempotent
    late = utcnow() > att.deadline_at + _grace()
    if not late and (session_id is None or not secrets.compare_digest(session_id, att.session_id)):
        raise AppError(409, "session_replaced", "This test was opened in another window or device. Reload to continue here.")
    _finish(db, att, sch, "timeout" if late else "manual", user, request)
    db.commit()
    return _summary(db, att, sch)


def auto_submit_overdue(db: Session) -> int:
    """Sweeper: close attempts whose deadline (plus grace) has passed even if the browser never came back."""
    rows = db.scalars(select(TestAttempt).where(TestAttempt.status == AttemptStatus.IN_PROGRESS, TestAttempt.deadline_at < utcnow() - _grace())).all()
    for att in rows:
        _finish(db, att, sched.get_schedule(db, att.schedule_id), "timeout", None)
    db.commit()
    return len(rows)


def sweep(db: Session) -> dict:
    return {"auto_submitted": auto_submit_overdue(db), "expired": sched.expire_missed(db)}


# ---- staff: recordings ------------------------------------------------------------------------------

def list_recordings(db: Session, user: User, schedule_id: int) -> list[RecordingOut]:
    sch = sched.staff_get(db, user, schedule_id)
    att = db.scalar(select(TestAttempt).where(TestAttempt.schedule_id == sch.id))
    if att is None:
        return []
    recs = db.scalars(select(AttemptRecording).where(AttemptRecording.attempt_id == att.id).order_by(AttemptRecording.question_id, AttemptRecording.attempt_no)).all()
    return [_rec_out(r) for r in recs]


def recording_file(db: Session, user: User, recording_id: int, request: Request):
    rec = db.get(AttemptRecording, recording_id)
    if rec is None:
        raise AppError(404, "not_found", "Recording not found.")
    att = db.get(TestAttempt, rec.attempt_id)
    assert att is not None
    sch = sched.get_schedule(db, att.schedule_id)
    sched.require_staff(db, user, sch)
    audit_service.log_action(db, "recording.accessed", actor=user, entity_type="attempt_recording", entity_id=rec.id, request=request)
    db.commit()
    try:
        return storage_service.path_for(rec.stored_name), rec.mime
    except ValueError as exc:
        raise AppError(404, "not_found", "Recording not found.") from exc

