"""Phase 6: evaluation, speech scoring, review / override / release, decisions and interviews."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import AuditLog, EvaluationResult, RecordingTranscript
from app.services import evaluation_service
from app.services.speech_scoring import compare
from app.speech import SpeechProviderError
from app.speech.mock_provider import MockSpeechProvider
from app.speech.openai_provider import OpenAISpeechProvider
from tests.conftest import applicant_client, new_client, recruiter, user_id
from tests.test_scheduling import accepted_start, approved_app, iso, make_schedule, publish, qs, seed_bank, sess  # noqa: F401

WEBM = b"\x1a\x45\xdf\xa3"


def marker(sentence: str, conf: float | None = None) -> bytes:
    tag = f"MOCKSTT[{conf}]:" if conf is not None else "MOCKSTT:"
    return WEBM + tag.encode() + sentence.encode() + b"\x00"


def snapshot(admin, d):
    snap = admin.get(f"/api/assessments/{d['id']}/versions/1").json()["snapshot"]
    return {q["question_id"]: q for s in snap["sections"] for q in s["questions"]}


def take(admin, ap, d, s, pick=lambda i, k: k["correct_index"], speak=None):
    """Run a whole test. `pick(i, key)` returns the option index (or None to skip); `speak(i, sentence)` returns audio bytes or None."""
    att = accepted_start(ap, s)
    keys = snapshot(admin, d)
    h = sess(att)
    answers = []
    for i, q in enumerate(qs(att, "mcq") + qs(att, "aptitude")):
        sel = pick(i, keys[q["id"]])
        if sel is not None:
            answers.append({"question_id": q["id"], "selected_index": sel, "seq": i + 1})
    if answers:
        assert ap.put(f"/api/attempts/{att['id']}/answers", headers=h, json={"answers": answers}).status_code == 200
    for i, q in enumerate(qs(att, "repeat_sentence")):
        if speak is None:
            continue
        sentence = ap.post(f"/api/attempts/{att['id']}/questions/{q['id']}/play", headers=h).json()["sentence"]
        audio = speak(i, sentence)
        if audio is not None:
            r = ap.post(f"/api/attempts/{att['id']}/questions/{q['id']}/recording", headers=h, files={"file": ("r.webm", audio, "audio/webm")})
            assert r.status_code == 201, r.text
    assert ap.post(f"/api/attempts/{att['id']}/submit", headers=h).status_code == 200
    return att


def eval_id(admin, s):
    e = admin.get(f"/api/schedules/{s['id']}").json()["evaluation_id"]
    assert e, "evaluation should be created when the test is submitted"
    return e


def ev(admin, eid):
    r = admin.get(f"/api/evaluations/{eid}")
    assert r.status_code == 200, r.text
    return r.json()


def items(e, kind):
    return [i for g in e["groups"] if g["kind"] == kind for i in g["items"]]


def section(e, kind):
    return [s for s in e["sections"] if s["kind"] == kind][0]


@pytest.fixture
def case(admin):
    o, ap, a = approved_app(admin)
    d = publish(admin, a)
    s = make_schedule(admin, a)
    return o, ap, a, d, s


# ------------------------------------------------------------------ pure scoring

def test_compare_exact_missing_substituted_extra_and_order():
    e = "Please send the revised drawings to the team today."
    assert compare(e, e)["accuracy"] == 1.0
    miss = compare(e, "please send revised drawings to team")
    assert miss["missing"] == ["the", "the", "today"] and miss["accuracy"] == pytest.approx(0.667, abs=0.001) and miss["completeness"] == pytest.approx(0.667, abs=0.001)
    sub = compare(e, "please send the revised plans to the team today")
    assert sub["substituted"] == [{"expected": "drawings", "heard": "plans"}] and sub["accuracy"] == pytest.approx(0.889, abs=0.001)
    fillers = compare(e, "um please send the the revised drawings to the team today thanks")
    assert fillers["accuracy"] == 1.0 and "um" in fillers["extra"]  # extra words are never penalised
    near = compare(e, "please send the revised drawing to the team today")
    assert near["near_matches"] == [{"expected": "drawings", "heard": "drawing"}] and 0.9 < near["accuracy"] < 1.0
    scrambled = compare(e, "today the team to drawings revised the send please")
    assert scrambled["order_differs"] is True and scrambled["accuracy"] < 0.4
    assert compare(e, "")["accuracy"] == 0.0
    assert compare("", "anything")["accuracy"] is None


def test_mock_speech_provider_never_invents_a_transcript():
    p = MockSpeechProvider()
    assert p.transcribe(WEBM + b"\x00" * 500, "audio/webm").text == ""
    t = p.transcribe(marker("hello there", 0.4), "audio/webm")
    assert (t.text, t.confidence) == ("hello there", 0.4)


def test_openai_provider_with_mocked_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions") and request.headers["authorization"] == "Bearer k"
        body = request.read()
        assert b"verbose_json" in body and b"expected" not in body  # the expected sentence is never sent
        return httpx.Response(200, json={"text": " hello world ", "segments": [{"avg_logprob": -0.1, "no_speech_prob": 0.01}, {"avg_logprob": -0.3, "no_speech_prob": 0.02}]})
    p = OpenAISpeechProvider("k", "whisper-1", "https://stt.example/v1", 5, transport=httpx.MockTransport(handler))
    t = p.transcribe(WEBM + b"x", "audio/webm")
    assert t.text == "hello world" and 0.78 < t.confidence < 0.84
    silent = OpenAISpeechProvider("k", "m", "https://stt.example/v1", 5, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "you", "segments": [{"avg_logprob": -0.05, "no_speech_prob": 0.9}]})))
    assert silent.transcribe(b"x", "audio/webm").confidence <= 0.3
    bad = OpenAISpeechProvider("k", "m", "https://stt.example/v1", 5, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SpeechProviderError):
        bad.transcribe(b"x", "audio/webm")
    with pytest.raises(SpeechProviderError):
        OpenAISpeechProvider("", "m", "https://stt.example/v1", 5)


# ------------------------------------------------------------------ objective evaluation

def test_objective_scoring_counts_and_no_negative_marking(admin, case):
    o, ap, a, d, s = case
    # every third answer correct, every third unanswered, the rest wrong
    take(admin, ap, d, s, pick=lambda i, k: k["correct_index"] if i % 3 == 0 else (None if i % 3 == 1 else (k["correct_index"] + 1) % len(k["options"])))
    e = ev(admin, eval_id(admin, s))
    keys = snapshot(admin, d)
    for kind in ("mcq", "aptitude"):
        its = items(e, kind)
        sec = section(e, kind)
        assert sec["correct"] + sec["incorrect"] + sec["unanswered"] == len(its)
        assert sec["obtained"] == sum(i["max_marks"] for i in its if i["is_correct"])
        assert all(i["final_marks"] == (i["max_marks"] if i["is_correct"] else 0) for i in its)  # never negative
        for i in its:
            assert i["correct_text"] == keys[i["question_id"]]["options"][keys[i["question_id"]]["correct_index"]]
    assert e["status"] == "draft" and e["total_marks"] > 0
    assert e["percentage"] == pytest.approx(round(e["total_obtained"] / e["total_marks"] * 100, 1))
    assert "not written by AI" in e["summary"] and e["time_taken_seconds"] is not None


def test_low_score_never_changes_the_application_status(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, pick=lambda i, k: (k["correct_index"] + 1) % len(k["options"]))
    e = ev(admin, eval_id(admin, s))
    assert e["total_obtained"] == 0 or e["percentage"] < 50
    assert admin.get(f"/api/applications/{a['id']}").json()["status"] == "approved"  # nothing was auto-rejected


# ------------------------------------------------------------------ speech evaluation

def test_confident_transcript_is_scored_automatically(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent))
    e = ev(admin, eval_id(admin, s))
    rs = items(e, "repeat_sentence")
    assert rs and all(i["stt_status"] == "ok" and i["final_marks"] == i["max_marks"] and not i["needs_review"] for i in rs)
    assert rs[0]["speech"]["accuracy"] == 1.0 and rs[0]["speech"]["is_mock"] is True and e["speech_is_mock"] is True
    assert e["blockers"] == [] and rs[0]["recordings"][0]["is_final"] is True


def test_omissions_reduce_the_score_and_are_listed(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(" ".join(sent.split()[:-2])))
    rs = items(ev(admin, eval_id(admin, s)), "repeat_sentence")
    for i in rs:
        assert 0 < i["final_marks"] < i["max_marks"] and len(i["speech"]["missing"]) == 2


def test_audio_the_mock_cannot_read_is_flagged_not_scored_and_blocks_approval(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: WEBM + b"\x00" * 300)
    eid = eval_id(admin, s)
    e = ev(admin, eid)
    rs = items(e, "repeat_sentence")
    assert all(i["stt_status"] == "low_confidence" and i["final_marks"] is None and i["auto_marks"] is None and i["needs_review"] for i in rs)
    assert section(e, "repeat_sentence")["unresolved"] == len(rs) and "not scored yet" in e["summary"]
    assert e["blockers"] and admin.post(f"/api/evaluations/{eid}/finalize").json()["error"]["code"] == "unresolved_items"
    assert admin.post(f"/api/evaluations/{eid}/items/{rs[0]['id']}/confirm", json={}).json()["error"]["code"] == "nothing_to_confirm"
    for i in rs:
        r = admin.post(f"/api/evaluations/{eid}/items/{i['id']}/override", json={"marks": i["max_marks"] / 2, "reason": "Listened: about half the sentence was repeated"})
        assert r.status_code == 200
    assert admin.post(f"/api/evaluations/{eid}/finalize").json()["status"] == "final"


def test_low_confidence_is_provisional_until_a_person_confirms(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent, 0.4))
    eid = eval_id(admin, s)
    rs = items(ev(admin, eid), "repeat_sentence")
    assert all(i["stt_status"] == "low_confidence" and i["auto_marks"] == i["max_marks"] and i["final_marks"] is None for i in rs)
    assert admin.post(f"/api/evaluations/{eid}/finalize").status_code == 409
    for i in rs:
        c = admin.post(f"/api/evaluations/{eid}/items/{i['id']}/confirm", json={"note": "Listened, matches"})
        assert c.status_code == 200
    e = ev(admin, eid)
    assert all(i["final_marks"] == i["max_marks"] and not i["needs_review"] for i in items(e, "repeat_sentence"))
    assert admin.post(f"/api/evaluations/{eid}/items/{rs[0]['id']}/confirm", json={}).status_code == 409


def test_missing_recording_scores_zero_but_a_reported_mic_problem_is_flagged(admin, case):
    o, ap, a, d, s = case
    att = accepted_start(ap, s)
    ap.post(f"/api/attempts/{att['id']}/events", headers=sess(att), json={"events": [{"kind": "mic_denied"}]})
    ap.post(f"/api/attempts/{att['id']}/submit", headers=sess(att))
    rs = items(ev(admin, eval_id(admin, s)), "repeat_sentence")
    assert all(i["stt_status"] == "no_recording" and i["final_marks"] == 0 and i["unanswered"] and i["needs_review"] and "microphone" in i["review_note"] for i in rs)


def test_missing_recording_without_a_reported_problem_is_not_flagged(admin):
    o, ap, a = approved_app(admin, email="quiet@gmail.com")
    publish(admin, a)
    s = make_schedule(admin, a)
    accepted = accepted_start(ap, s)
    ap.post(f"/api/attempts/{accepted['id']}/submit", headers=sess(accepted))
    rs = items(ev(admin, eval_id(admin, s)), "repeat_sentence")
    assert all(i["final_marks"] == 0 and not i["needs_review"] for i in rs)


def test_rerun_speech_and_backfill(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: WEBM + b"\x00" * 300)
    eid = eval_id(admin, s)
    r = admin.post(f"/api/evaluations/{eid}/rerun-speech")
    assert r.status_code == 200 and all(i["stt_status"] == "low_confidence" for i in items(r.json(), "repeat_sentence"))
    with SessionLocal() as db:
        db.execute(text("delete from evaluation_results"))
        db.commit()
    assert admin.get(f"/api/schedules/{s['id']}").json()["evaluation_id"] is None
    made = admin.post(f"/api/schedules/{s['id']}/evaluation")
    assert made.status_code == 200 and made.json()["total_marks"] > 0
    again = admin.post(f"/api/schedules/{s['id']}/evaluation")
    assert again.json()["id"] == made.json()["id"]  # idempotent
    with SessionLocal() as db:
        db.execute(text("delete from evaluation_results"))
        db.commit()
        assert evaluation_service.sweep(db)["evaluations_created"] == 1


def test_evaluation_needs_a_submitted_test(admin, case):
    o, ap, a, d, s = case
    assert admin.post(f"/api/schedules/{s['id']}/evaluation").json()["error"]["code"] == "not_submitted"


# ------------------------------------------------------------------ overrides, comments, finalise, release

def done(admin, case, **kw):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent), **kw)
    return eval_id(admin, s)


def test_override_records_who_when_original_revised_and_reason(admin, case):
    eid = done(admin, case)
    e = ev(admin, eid)
    item = items(e, "mcq")[0]
    assert admin.post(f"/api/evaluations/{eid}/items/{item['id']}/override", json={"marks": 1, "reason": "no"}).status_code == 422  # reason too short
    assert admin.post(f"/api/evaluations/{eid}/items/{item['id']}/override", json={"marks": item["max_marks"] + 5, "reason": "Too generous mark"}).json()["error"]["code"] == "marks_too_high"
    assert admin.post(f"/api/evaluations/{eid}/items/{item['id']}/override", json={"marks": -1, "reason": "Negative marks"}).status_code == 422
    r = admin.post(f"/api/evaluations/{eid}/items/{item['id']}/override", json={"marks": 0, "reason": "Question was ambiguous, accepted by panel"})
    assert r.status_code == 200
    e2 = r.json()
    changed = [i for i in items(e2, "mcq") if i["id"] == item["id"]][0]
    assert changed["final_marks"] == 0 and changed["overridden"] and changed["auto_marks"] == item["auto_marks"]
    o = e2["overrides"][0]
    assert o["original_marks"] == item["final_marks"] and o["revised_marks"] == 0 and o["reason"].startswith("Question was ambiguous") and o["changed_by"] and o["changed_at"]
    assert e2["total_obtained"] == e["total_obtained"] - item["final_marks"]
    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.action == "evaluation.score_overridden")).all()


def test_comments_are_internal_and_listed(admin, case):
    eid = done(admin, case)
    r = admin.post(f"/api/evaluations/{eid}/comments", json={"body": "Strong fundamentals, hesitant on speaking."})
    assert r.status_code == 201 and r.json()["comments"][0]["body"].startswith("Strong") and r.json()["comments"][0]["author"]
    assert admin.post(f"/api/evaluations/{eid}/comments", json={"body": ""}).status_code == 422


def test_final_evaluations_are_locked_until_reopened(admin, case):
    eid = done(admin, case)
    item = items(ev(admin, eid), "mcq")[0]
    assert admin.post(f"/api/evaluations/{eid}/finalize").json()["finalized_at"]
    assert admin.post(f"/api/evaluations/{eid}/items/{item['id']}/override", json={"marks": 0, "reason": "Trying to edit"}).json()["error"]["code"] == "evaluation_final"
    assert admin.post(f"/api/evaluations/{eid}/finalize").status_code == 409
    assert admin.post(f"/api/evaluations/{eid}/reopen", json={"reason": "x"}).status_code == 422
    r = admin.post(f"/api/evaluations/{eid}/reopen", json={"reason": "Found a marking error"})
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["comments"][0]["body"].startswith("Reopened")


def test_release_flow_applicant_sees_only_released_scores(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent))
    eid = eval_id(admin, s)
    admin.post(f"/api/evaluations/{eid}/comments", json={"body": "INTERNAL-NOTE-XYZ"})
    assert ap.get("/api/my-results").json() == [] and ap.get(f"/api/my-results/{eid}").status_code == 404
    assert admin.post(f"/api/evaluations/{eid}/release", json={}).json()["error"]["code"] == "not_final"
    admin.post(f"/api/evaluations/{eid}/finalize")
    assert ap.get("/api/my-results").json() == []  # final but not released
    r = admin.post(f"/api/evaluations/{eid}/release", json={"feedback": "Good effort. Work on speaking pace."})
    assert r.status_code == 200 and r.json()["released_at"]
    assert admin.post(f"/api/evaluations/{eid}/release", json={}).json()["error"]["code"] == "already_released"
    mine = ap.get(f"/api/my-results/{eid}")
    assert mine.status_code == 200
    body = mine.json()
    blob = json.dumps(body)
    assert body["feedback"] == "Good effort. Work on speaking pace." and body["total_obtained"] > 0 and {x["kind"] for x in body["sections"]} == {"mcq", "aptitude", "repeat_sentence"}
    for secret in ("INTERNAL-NOTE-XYZ", "correct_index", "correct_text", "explanation", "recognized", "overrides", "comments", "candidate_email"):
        assert secret not in blob
    assert any(n["type"] == "result_released" for n in ap.get("/api/notifications").json()["items"])
    other = applicant_client("other@gmail.com")
    assert other.get(f"/api/my-results/{eid}").status_code == 404 and other.get("/api/my-results").json() == []
    assert admin.post(f"/api/evaluations/{eid}/reopen", json={"reason": "Need to edit"}).json()["error"]["code"] == "already_released"
    w = admin.post(f"/api/evaluations/{eid}/withdraw-release", json={"reason": "Released by mistake"})
    assert w.status_code == 200 and w.json()["released_at"] is None
    assert ap.get(f"/api/my-results/{eid}").status_code == 404


def test_evaluation_permissions_and_scope(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent))
    eid = eval_id(admin, s)
    assert ap.get("/api/evaluations").status_code == 404 and ap.get(f"/api/evaluations/{eid}").status_code == 404
    assert new_client().get("/api/evaluations").status_code == 401
    noperm = recruiter(admin, "np@solidpro-test.com", perms=("review_applications",))
    rev = recruiter(admin, "rev@solidpro-test.com", perms=("review_results",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(noperm)]})
    assert noperm.get("/api/evaluations").status_code == 403
    assert rev.get(f"/api/evaluations/{eid}").status_code == 404  # has the permission, not assigned
    assert rev.get("/api/evaluations").json()["total"] == 0
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(noperm), user_id(rev)]})
    assert rev.get(f"/api/evaluations/{eid}").status_code == 200 and rev.get("/api/evaluations").json()["total"] == 1
    assert rev.post(f"/api/evaluations/{eid}/comments", json={"body": "ok"}).status_code == 201


def test_list_filters(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: WEBM + b"\x00" * 300)
    assert admin.get("/api/evaluations", params={"needs_review": True}).json()["total"] == 1
    assert admin.get("/api/evaluations", params={"status": "final"}).json()["total"] == 0
    assert admin.get("/api/evaluations", params={"released": False, "search": "Jane"}).json()["total"] == 1
    assert admin.get("/api/evaluations", params={"released": True}).json()["total"] == 0


# ------------------------------------------------------------------ decisions

def test_decisions_are_human_ordered_and_explained(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent))
    eid = eval_id(admin, s)
    dec = lambda decision, reason=None: admin.post(f"/api/applications/{a['id']}/decision", json={"decision": decision, "reason": reason})  # noqa: E731
    assert dec("shortlist").json()["error"]["code"] == "evaluation_required"
    assert dec("select").json()["error"]["code"] == "invalid_state"
    admin.post(f"/api/evaluations/{eid}/finalize")
    r = dec("shortlist", "Strong technical score")
    assert r.status_code == 200 and r.json()["status"] == "shortlisted"
    assert dec("shortlist").status_code == 409
    assert any(n["type"] == "application_shortlisted" for n in ap.get("/api/notifications").json()["items"])
    assert dec("select", "Great interview").json()["status"] == "selected"
    assert dec("reject", "Position filled").status_code == 409  # selected is final here
    hist = admin.get(f"/api/applications/{a['id']}").json()
    assert hist["status"] == "selected"


def test_reject_needs_a_real_reason_and_is_visible_to_the_applicant(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s)
    dec = lambda reason: admin.post(f"/api/applications/{a['id']}/decision", json={"decision": "reject", "reason": reason})  # noqa: E731
    assert dec(None).status_code == 422 and dec("no").status_code == 422
    r = dec("Did not meet the role requirements after review")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert dec("again please for reason").status_code == 409
    assert any(n["type"] == "application_rejected" for n in ap.get("/api/notifications").json()["items"])


def test_applicants_and_unpermitted_staff_cannot_decide(admin, case):
    o, ap, a, d, s = case
    body = {"decision": "reject", "reason": "Trying to reject"}
    assert ap.post(f"/api/applications/{a['id']}/decision", json=body).status_code == 404
    noperm = recruiter(admin, "np2@solidpro-test.com", perms=("review_applications",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(noperm)]})
    assert noperm.post(f"/api/applications/{a['id']}/decision", json=body).status_code == 403


# ------------------------------------------------------------------ interviews

def shortlisted(admin, case):
    o, ap, a, d, s = case
    take(admin, ap, d, s, speak=lambda i, sent: marker(sent))
    eid = eval_id(admin, s)
    admin.post(f"/api/evaluations/{eid}/finalize")
    assert admin.post(f"/api/applications/{a['id']}/decision", json={"decision": "shortlist"}).status_code == 200
    return o, ap, a


def test_interview_needs_a_shortlisted_candidate_and_valid_inputs(admin, case):
    o, ap, a, d, s = case
    body = {"application_id": a["id"], "scheduled_start": iso(48)}
    assert admin.post("/api/interviews", json=body).json()["error"]["code"] == "not_shortlisted"
    shortlisted(admin, case)
    assert admin.post("/api/interviews", json={**body, "scheduled_start": "2030-01-01T10:00:00"}).status_code == 422  # naive time
    assert admin.post("/api/interviews", json={**body, "scheduled_start": iso(-2)}).json()["error"]["code"] == "start_in_past"
    assert admin.post("/api/interviews", json={**body, "meeting_link": "javascript:alert(1)"}).status_code == 422
    assert admin.post("/api/interviews", json={**body, "interviewer_id": user_id(ap)}).json()["error"]["code"] == "bad_interviewer"  # an applicant cannot interview
    assert ap.post("/api/interviews", json=body).status_code == 404


def test_interview_lifecycle_and_applicant_visibility(admin, case):
    o, ap, a = shortlisted(admin, case)
    boss = recruiter(admin, "iv@solidpro-test.com", perms=("manage_interviews",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(boss)]})
    r = boss.post("/api/interviews", json={"application_id": a["id"], "interviewer_id": user_id(boss), "scheduled_start": iso(48), "interview_type": "technical", "mode": "online",
                                          "meeting_link": "https://meet.example/abc", "instructions": "Keep your ID ready"})
    assert r.status_code == 201 and r.json()["status"] == "scheduled"
    iid = r.json()["id"]
    mine = ap.get("/api/my-interviews").json()
    assert len(mine) == 1 and mine[0]["meeting_link"] == "https://meet.example/abc" and mine[0]["instructions"] == "Keep your ID ready"
    assert any(n["type"] == "interview_scheduled" for n in ap.get("/api/notifications").json()["items"])
    assert any(n["type"] == "interview_assigned" for n in boss.get("/api/notifications").json()["items"])
    # reschedule
    rr = boss.patch(f"/api/interviews/{iid}", json={"scheduled_start": iso(72)})
    assert rr.status_code == 200 and rr.json()["status"] == "rescheduled"
    assert any(n["type"] == "interview_rescheduled" for n in ap.get("/api/notifications").json()["items"])
    # feedback, internal only
    fb = {"technical_feedback": "Solid on CAD APIs", "communication_feedback": "Clear", "strengths": "SECRET-STRENGTH", "improvements": "Testing", "recommendation": "yes"}
    f = boss.put(f"/api/interviews/{iid}/feedback", json=fb)
    assert f.status_code == 200 and f.json()["status"] == "completed" and f.json()["feedback"]["recommendation"] == "yes"
    assert "SECRET-STRENGTH" not in json.dumps(ap.get("/api/my-interviews").json()) and ap.get(f"/api/interviews/{iid}").status_code == 404
    assert boss.put(f"/api/interviews/{iid}/feedback", json={**fb, "recommendation": "strong_yes"}).json()["feedback"]["recommendation"] == "strong_yes"
    assert boss.patch(f"/api/interviews/{iid}", json={"instructions": "x"}).status_code == 409  # completed
    assert boss.post(f"/api/interviews/{iid}/cancel", json={"reason": "too late"}).status_code == 409
    assert ap.get("/api/my-interviews").json()[0]["status"] == "completed"
    assert ap.get("/api/my-interviews").json()[0]["meeting_link"] is None  # no link once finished


def test_cancel_hides_details_and_pending_has_no_time(admin, case):
    o, ap, a = shortlisted(admin, case)
    pending = admin.post("/api/interviews", json={"application_id": a["id"]})
    assert pending.status_code == 201 and pending.json()["status"] == "pending" and pending.json()["scheduled_start"] is None
    iid = pending.json()["id"]
    sched = admin.patch(f"/api/interviews/{iid}", json={"scheduled_start": iso(30), "meeting_link": "https://meet.example/x"})
    assert sched.json()["status"] == "scheduled"  # first time set: scheduled, not rescheduled
    c = admin.post(f"/api/interviews/{iid}/cancel", json={"reason": "Panel unavailable"})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    mine = ap.get("/api/my-interviews").json()[0]
    assert mine["status"] == "cancelled" and mine["meeting_link"] is None
    assert any(n["type"] == "interview_cancelled" for n in ap.get("/api/notifications").json()["items"])
    assert admin.post(f"/api/interviews/{iid}/complete").status_code == 409


def test_interview_access_rules(admin, case):
    o, ap, a = shortlisted(admin, case)
    interviewer = recruiter(admin, "only@solidpro-test.com", perms=())  # no manage_interviews
    stranger = recruiter(admin, "stranger@solidpro-test.com", perms=("manage_interviews",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(interviewer)]})
    iv = admin.post("/api/interviews", json={"application_id": a["id"], "interviewer_id": user_id(interviewer), "scheduled_start": iso(24)}).json()
    # the assigned interviewer can see it and give feedback, but not manage it
    assert interviewer.get(f"/api/interviews/{iv['id']}").json()["can_manage"] is False
    assert interviewer.patch(f"/api/interviews/{iv['id']}", json={"instructions": "x"}).status_code == 403
    assert interviewer.post("/api/interviews", json={"application_id": a["id"]}).status_code == 403
    assert interviewer.get("/api/interviews").json()["total"] == 1
    assert interviewer.put(f"/api/interviews/{iv['id']}/feedback", json={"recommendation": "neutral"}).status_code == 200
    # an employee with the permission but no access to the opening sees nothing
    assert stranger.get(f"/api/interviews/{iv['id']}").status_code == 404
    assert stranger.get("/api/interviews").json()["total"] == 0
    assert stranger.put(f"/api/interviews/{iv['id']}/feedback", json={"recommendation": "no"}).status_code == 404
    assert new_client().get("/api/interviews").status_code == 401


def test_sanity_helpers_used_by_other_phases(admin):
    assert datetime.now(UTC) + timedelta(hours=1) > datetime.now(UTC)
    with SessionLocal() as db:
        assert db.scalars(select(EvaluationResult)).all() == []
        assert db.scalars(select(RecordingTranscript)).all() == []
