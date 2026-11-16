"""Phase 5: scheduling, invitations, accept / reschedule, online test taking, Repeat-the-Sentence recordings."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import AuditLog, EmailLog, TestAttempt
from app.models.base import utcnow
from app.services import attempt_service
from app.services.question_bank_service import sync_seed_bank
from tests.conftest import applicant_client, new_client, recruiter, user_id
from tests.test_assessments import approved_app, generate, ready

AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 200


@pytest.fixture(autouse=True)
def seed_bank():
    with SessionLocal() as db:
        sync_seed_bank(db)
        db.commit()


def iso(delta_hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=delta_hours)).isoformat()


def publish(admin, a, **cfg):
    d = generate(admin, a["id"], **cfg)
    ready(admin, d)
    assert admin.post(f"/api/assessments/{d['id']}/approve", json={}).status_code == 200
    assert admin.post(f"/api/assessments/{d['id']}/versions/1/publish").status_code == 200
    return d


def make_schedule(admin, a, start=-0.1, end=3, **kw):
    r = admin.post("/api/schedules", json={"application_id": a["id"], "window_start": iso(start), "window_end": iso(end), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def invite_token(email: str) -> str:
    with SessionLocal() as db:
        log = db.scalars(select(EmailLog).where(EmailLog.to_email == email, EmailLog.template == "test_invitation").order_by(EmailLog.id.desc())).first()
        assert log is not None
        return re.search(r"/test/([A-Za-z0-9_\-]+)", log.body_text).group(1)


@pytest.fixture
def case(admin):
    o, ap, a = approved_app(admin)
    d = publish(admin, a)
    s = make_schedule(admin, a)
    return admin, ap, a, d, s


def start(ap, s, consent=True):
    return ap.post(f"/api/test-invitations/{s['id']}/start", json={"consent": consent})


def accepted_start(ap, s):
    assert ap.post(f"/api/test-invitations/{s['id']}/accept").status_code == 200
    r = start(ap, s)
    assert r.status_code == 200, r.text
    return r.json()


def sess(att):
    return {"X-Attempt-Session": att["session_id"]}


def qs(att, kind):
    return [q for sec in att["sections"] if sec["kind"] == kind for q in sec["questions"]]


# ------------------------------------------------------------------ creating schedules

def test_schedule_needs_approved_application_and_published_version(admin):
    o, ap, a = approved_app(admin)
    body = {"application_id": a["id"], "window_start": iso(1), "window_end": iso(5)}
    r = admin.post("/api/schedules", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_published_assessment"
    d = generate(admin, a["id"])
    ready(admin, d)
    admin.post(f"/api/assessments/{d['id']}/approve", json={})
    assert admin.post("/api/schedules", json=body).status_code == 409  # approved but not published
    admin.post(f"/api/assessments/{d['id']}/versions/1/publish")
    assert admin.post("/api/schedules", json=body).status_code == 201


def test_window_validation_and_single_active_schedule(admin):
    _, _, a = approved_app(admin)
    publish(admin, a)
    base = {"application_id": a["id"]}
    assert admin.post("/api/schedules", json={**base, "window_start": "2030-01-01T10:00:00", "window_end": "2030-01-01T12:00:00"}).status_code == 422  # naive time
    assert admin.post("/api/schedules", json={**base, "window_start": iso(5), "window_end": iso(1)}).status_code == 422
    assert admin.post("/api/schedules", json={**base, "window_start": iso(-5), "window_end": iso(-1)}).json()["error"]["code"] == "window_in_past"
    r = admin.post("/api/schedules", json={**base, "window_start": iso(1), "window_end": iso(1.1)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "window_too_short"
    make_schedule(admin, a)
    assert admin.post("/api/schedules", json={**base, "window_start": iso(1), "window_end": iso(6)}).json()["error"]["code"] == "schedule_exists"


def test_link_is_emailed_once_and_stored_hashed(case):
    admin, ap, a, d, s = case
    assert s["invite_link"].startswith("http://localhost:5173/test/")
    token = s["invite_link"].rsplit("/", 1)[1]
    assert invite_token("cand@gmail.com") == token
    assert admin.get(f"/api/schedules/{s['id']}").json()["invite_link"] is None
    with SessionLocal() as db:
        row = db.execute(text("select token_hash from assessment_schedules")).scalar_one()
        assert row != token and len(row) == 64
    notes = ap.get("/api/notifications").json()
    assert any(n["type"] == "test_invitation" for n in (notes["items"] if isinstance(notes, dict) else notes))


def test_staff_permissions_and_scope(admin):
    o, _, a = approved_app(admin)
    publish(admin, a)
    nobody = recruiter(admin, "nobody@solidpro-test.com", perms=("review_applications",))
    sched_emp = recruiter(admin, "sched@solidpro-test.com", perms=("schedule_tests",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(nobody)]})
    body = {"application_id": a["id"], "window_start": iso(1), "window_end": iso(5)}
    assert nobody.post("/api/schedules", json=body).status_code == 403
    assert sched_emp.post("/api/schedules", json=body).status_code == 404  # has the permission, not assigned
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(nobody), user_id(sched_emp)]})
    assert sched_emp.post("/api/schedules", json=body).status_code == 201
    assert sched_emp.get("/api/schedules").json()["total"] == 1
    assert nobody.get("/api/schedules").status_code == 403


# ------------------------------------------------------------------ applicant invitations

def test_applicants_only_see_their_own_invitations(case):
    admin, ap, a, d, s = case
    other = applicant_client("other@gmail.com")
    assert len(ap.get("/api/test-invitations").json()) == 1
    assert other.get("/api/test-invitations").json() == []
    assert other.get(f"/api/test-invitations/{s['id']}").status_code == 404
    assert other.post(f"/api/test-invitations/{s['id']}/accept").status_code == 404
    assert other.get("/api/schedules").status_code == 404
    assert new_client().get("/api/test-invitations").status_code == 401
    inv = ap.get(f"/api/test-invitations/{s['id']}").json()
    assert "correct_index" not in str(inv) and not any("text" in sec for sec in inv["sections"])


def test_token_link_only_works_for_the_invited_applicant_and_resend_rotates_it(case):
    admin, ap, a, d, s = case
    token = invite_token("cand@gmail.com")
    other = applicant_client("other@gmail.com")
    assert other.get(f"/api/test-invitations/by-token/{token}").status_code == 404
    assert ap.get(f"/api/test-invitations/by-token/{token}").json()["id"] == s["id"]
    assert ap.get("/api/test-invitations/by-token/nonsense").status_code == 404
    r = admin.post(f"/api/schedules/{s['id']}/resend")
    assert r.status_code == 200
    new = r.json()["invite_link"].rsplit("/", 1)[1]
    assert new != token
    assert ap.get(f"/api/test-invitations/by-token/{token}").status_code == 404
    assert ap.get(f"/api/test-invitations/by-token/{new}").status_code == 200


def test_expired_link_is_410(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=1, end=5, link_expires_at=iso(2))
    with SessionLocal() as db:
        db.execute(text("update assessment_schedules set link_expires_at = now() - interval '1 minute'"))
        db.commit()
    r = ap.get(f"/api/test-invitations/by-token/{s['invite_link'].rsplit('/', 1)[1]}")
    assert r.status_code == 410 and r.json()["error"]["code"] == "link_expired"


def test_accept_is_idempotent_and_start_rules(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=2, end=6)
    assert start(ap, s).json()["error"]["code"] == "not_startable"  # not accepted yet
    assert ap.post(f"/api/test-invitations/{s['id']}/accept").json()["status"] == "accepted"
    assert ap.post(f"/api/test-invitations/{s['id']}/accept").json()["status"] == "accepted"
    assert start(ap, s, consent=False).json()["error"]["code"] == "consent_required"
    r = start(ap, s)
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_early"
    inv = ap.get(f"/api/test-invitations/{s['id']}").json()
    assert inv["can_start"] is False and "opens" in inv["start_blocked_reason"]


def test_missed_window_expires(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a)
    ap.post(f"/api/test-invitations/{s['id']}/accept")
    with SessionLocal() as db:
        db.execute(text("update assessment_schedules set window_end = now() - interval '1 minute'"))
        db.commit()
    assert start(ap, s).json()["error"]["code"] == "not_startable"
    assert ap.get(f"/api/test-invitations/{s['id']}").json()["status"] == "expired"
    # an expired schedule frees the application for a new one
    assert admin.post("/api/schedules", json={"application_id": a["id"], "window_start": iso(1), "window_end": iso(5)}).status_code == 201


def test_sweeper_expires_missed_and_auto_submits_overdue(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a)
    att = accepted_start(ap, s)
    with SessionLocal() as db:
        db.execute(text("update test_attempts set deadline_at = now() - interval '5 minutes'"))
        db.commit()
        assert attempt_service.sweep(db) == {"auto_submitted": 1, "expired": 0}
    d = admin.get(f"/api/schedules/{s['id']}").json()
    assert d["status"] == "completed" and d["attempt"]["submit_reason"] == "timeout"
    assert ap.get(f"/api/attempts/{att['id']}").json()["status"] == "submitted"


# ------------------------------------------------------------------ taking the test

def test_attempt_never_exposes_answer_keys_or_the_sentence(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    blob = str(att)
    for forbidden in ("correct_index", "explanation", "correct", "sha256"):
        assert forbidden not in blob
    assert all(q["text"] for q in qs(att, "mcq")) and all(len(q["options"]) >= 2 for q in qs(att, "mcq"))
    rs = qs(att, "repeat_sentence")
    assert rs and all(q["text"] is None and q["options"] is None for q in rs)
    assert att["session_id"] and att["deadline_at"] > att["server_now"]
    assert ap.get(f"/api/attempts/{att['id']}").json()["session_id"] is None


def test_options_are_shuffled_per_attempt_but_ids_stay_original(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    snap = admin.get(f"/api/assessments/{d['id']}/versions/1").json()["snapshot"]
    originals = {q["question_id"]: q for sec in snap["sections"] for q in sec["questions"]}
    for q in qs(att, "mcq"):
        o = originals[q["id"]]
        assert sorted(x["id"] for x in q["options"]) == list(range(len(o["options"])))
        assert all(x["text"] == o["options"][x["id"]] for x in q["options"])


def test_autosave_is_idempotent_ordered_and_validated(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    h, q = sess(att), qs(att, "mcq")[0]
    url = f"/api/attempts/{att['id']}/answers"
    put = lambda **kw: ap.put(url, headers=h, json={"answers": [{"question_id": q["id"], **kw}]})  # noqa: E731
    assert put(selected_index=1, seq=5).status_code == 200
    assert put(selected_index=0, seq=3).status_code == 200  # stale, ignored
    cur = [x for x in qs(ap.get(f"/api/attempts/{att['id']}").json(), "mcq") if x["id"] == q["id"]][0]
    assert cur["selected"] == 1
    assert put(selected_index=2, seq=6, marked_for_review=True).status_code == 200
    cur = [x for x in qs(ap.get(f"/api/attempts/{att['id']}").json(), "mcq") if x["id"] == q["id"]][0]
    assert cur["selected"] == 2 and cur["marked"] is True
    assert put(selected_index=99, seq=7).json()["error"]["code"] == "bad_answer"
    assert ap.put(url, headers=h, json={"answers": [{"question_id": 999999, "selected_index": 0, "seq": 1}]}).json()["error"]["code"] == "unknown_question"
    rs = qs(att, "repeat_sentence")[0]
    assert ap.put(url, headers=h, json={"answers": [{"question_id": rs["id"], "selected_index": 0, "seq": 1}]}).status_code == 422
    assert ap.put(url, json={"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 9}]}).json()["error"]["code"] == "session_replaced"


def test_second_window_takes_over_and_the_first_is_refused(case):
    admin, ap, a, d, s = case
    first = accepted_start(ap, s)
    second = start(ap, s).json()
    assert second["id"] == first["id"] and second["session_id"] != first["session_id"]
    q = qs(first, "mcq")[0]
    body = {"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 1}]}
    assert ap.put(f"/api/attempts/{first['id']}/answers", headers=sess(first), json=body).json()["error"]["code"] == "session_replaced"
    assert ap.put(f"/api/attempts/{first['id']}/answers", headers=sess(second), json=body).status_code == 200


def test_other_applicants_cannot_touch_an_attempt(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    other = applicant_client("other@gmail.com")
    q = qs(att, "mcq")[0]
    assert other.get(f"/api/attempts/{att['id']}").status_code == 404
    assert other.put(f"/api/attempts/{att['id']}/answers", headers=sess(att), json={"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 1}]}).status_code == 404
    assert other.post(f"/api/attempts/{att['id']}/submit", headers=sess(att)).status_code == 404
    assert admin.get(f"/api/attempts/{att['id']}").status_code == 404  # staff use schedule endpoints


def test_time_is_enforced_on_the_server(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    q = qs(att, "mcq")[0]
    with SessionLocal() as db:
        db.execute(text("update test_attempts set deadline_at = now() - interval '5 minutes'"))
        db.commit()
    r = ap.put(f"/api/attempts/{att['id']}/answers", headers=sess(att), json={"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 1}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "time_up"
    done = ap.get(f"/api/attempts/{att['id']}").json()
    assert done["status"] == "submitted" and done["sections"] == []
    assert admin.get(f"/api/schedules/{s['id']}").json()["attempt"]["submit_reason"] == "timeout"
    assert start(ap, s).json()["error"]["code"] == "already_submitted"


def test_grace_period_accepts_a_save_just_after_the_deadline(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    q = qs(att, "mcq")[0]
    with SessionLocal() as db:
        db.execute(text("update test_attempts set deadline_at = now() - interval '3 seconds'"))
        db.commit()
    r = ap.put(f"/api/attempts/{att['id']}/answers", headers=sess(att), json={"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 1}]})
    assert r.status_code == 200


def test_submit_is_idempotent_and_locks_the_attempt(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    q = qs(att, "mcq")[0]
    ap.put(f"/api/attempts/{att['id']}/answers", headers=sess(att), json={"answers": [{"question_id": q["id"], "selected_index": 0, "seq": 1}]})
    r1 = ap.post(f"/api/attempts/{att['id']}/submit", headers=sess(att))
    r2 = ap.post(f"/api/attempts/{att['id']}/submit", headers=sess(att))
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["submit_reason"] == "manual" and r1.json()["answered"] == 1
    assert r1.json()["submitted_at"] == r2.json()["submitted_at"]
    assert ap.put(f"/api/attempts/{att['id']}/answers", headers=sess(att), json={"answers": [{"question_id": q["id"], "selected_index": 1, "seq": 2}]}).json()["error"]["code"] == "attempt_closed"
    inv = ap.get(f"/api/test-invitations/{s['id']}").json()
    assert inv["status"] == "completed" and inv["can_start"] is False
    assert any(n["type"] == "test_submitted" for n in admin.get("/api/notifications").json()["items"])


# ------------------------------------------------------------------ repeat the sentence

def test_play_is_counted_on_the_server_and_reveals_the_sentence(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a, rs_max_replays=1)
    s = make_schedule(admin, a)
    att = accepted_start(ap, s)
    rs = qs(att, "repeat_sentence")[0]
    assert rs["plays_allowed"] == 2 and rs["plays_used"] == 0
    url = f"/api/attempts/{att['id']}/questions/{rs['id']}/play"
    r1 = ap.post(url, headers=sess(att))
    assert r1.status_code == 200 and r1.json()["sentence"] and r1.json()["plays_used"] == 1
    assert ap.post(url, headers=sess(att)).json()["plays_used"] == 2
    assert ap.post(url, headers=sess(att)).json()["error"]["code"] == "no_plays_left"
    assert qs(ap.get(f"/api/attempts/{att['id']}").json(), "repeat_sentence")[0]["plays_used"] == 2
    mcq = qs(att, "mcq")[0]
    assert ap.post(f"/api/attempts/{att['id']}/questions/{mcq['id']}/play", headers=sess(att)).status_code == 404


def test_recording_rules(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a, rs_max_attempts=2, rs_record_seconds=15)
    s = make_schedule(admin, a)
    att = accepted_start(ap, s)
    rs = qs(att, "repeat_sentence")[0]
    rec = f"/api/attempts/{att['id']}/questions/{rs['id']}/recording"
    up = lambda data=AUDIO, **form: ap.post(rec, headers=sess(att), files={"file": ("r.webm", data, "audio/webm")}, data=form)  # noqa: E731
    assert up().json()["error"]["code"] == "play_first"
    ap.post(f"/api/attempts/{att['id']}/questions/{rs['id']}/play", headers=sess(att))
    assert up(b"").json()["error"]["code"] == "empty_recording"
    assert up(b"MZ" + b"\x00" * 100).json()["error"]["code"] == "bad_audio"  # not audio, whatever the filename says
    assert up(AUDIO, duration_ms="60000").json()["error"]["code"] == "recording_too_long"
    ok = up(AUDIO, duration_ms="9000")
    assert ok.status_code == 201 and ok.json()["attempt_no"] == 1 and ok.json()["mime"] == "audio/webm"
    assert up().json()["attempt_no"] == 2
    assert up().json()["error"]["code"] == "no_recordings_left"
    cur = qs(ap.get(f"/api/attempts/{att['id']}").json(), "repeat_sentence")[0]
    assert cur["recordings_used"] == 2 and cur["recordings_allowed"] == 2
    assert "stored_name" not in str(ok.json())


def test_oversized_recording_is_refused(admin, monkeypatch):
    from app.core import config
    monkeypatch.setenv("MAX_RECORDING_MB", "1")
    config.get_settings.cache_clear()
    try:
        _, ap, a = approved_app(admin)
        publish(admin, a)
        s = make_schedule(admin, a)
        att = accepted_start(ap, s)
        rs = qs(att, "repeat_sentence")[0]
        ap.post(f"/api/attempts/{att['id']}/questions/{rs['id']}/play", headers=sess(att))
        r = ap.post(f"/api/attempts/{att['id']}/questions/{rs['id']}/recording", headers=sess(att), files={"file": ("r.webm", AUDIO + b"\x00" * 1_100_000, "audio/webm")})
        assert r.status_code == 413
    finally:
        config.get_settings.cache_clear()


def test_staff_playback_is_scoped_and_audited_and_applicants_cannot_use_it(admin):
    o, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a)
    att = accepted_start(ap, s)
    rs = qs(att, "repeat_sentence")[0]
    ap.post(f"/api/attempts/{att['id']}/questions/{rs['id']}/play", headers=sess(att))
    rid = ap.post(f"/api/attempts/{att['id']}/questions/{rs['id']}/recording", headers=sess(att), files={"file": ("r.webm", AUDIO, "audio/webm")}).json()["id"]
    r = admin.get(f"/api/recordings/{rid}/file")
    assert r.status_code == 200 and r.content == AUDIO and r.headers["content-type"] == "audio/webm"
    assert "no-store" in r.headers["cache-control"]
    assert [x["id"] for x in admin.get(f"/api/schedules/{s['id']}/recordings").json()] == [rid]
    assert ap.get(f"/api/recordings/{rid}/file").status_code == 404
    assert ap.get(f"/api/schedules/{s['id']}/recordings").status_code == 404
    unassigned = recruiter(admin, "un@solidpro-test.com", perms=("schedule_tests",))
    assert unassigned.get(f"/api/recordings/{rid}/file").status_code == 404
    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.action == "recording.accessed")).all()


# ------------------------------------------------------------------ monitoring events never punish

def test_client_events_are_recorded_for_context_and_change_nothing(case):
    admin, ap, a, d, s = case
    att = accepted_start(ap, s)
    ev = lambda *kinds: ap.post(f"/api/attempts/{att['id']}/events", headers=sess(att), json={"events": [{"kind": k} for k in kinds]})  # noqa: E731
    assert ev("tab_hidden", "tab_visible", "copy", "paste", "offline", "online").json() == {"recorded": 6}
    assert ev("keylogger").status_code == 422  # whitelist only
    after = ap.get(f"/api/attempts/{att['id']}").json()
    assert after["status"] == "in_progress"
    inv = ap.get(f"/api/test-invitations/{s['id']}").json()
    assert inv["status"] == "in_progress" and inv["can_start"] is True
    events = admin.get(f"/api/schedules/{s['id']}").json()["events"]
    client = [e for e in events if e["client_reported"]]
    assert len(client) == 6 and all(e["kind"].startswith("client_") for e in client)
    assert ap.post(f"/api/attempts/{att['id']}/events", headers=sess(att), json={"events": [{"kind": "copy"}] * 51}).status_code == 422
    assert ap.post(f"/api/attempts/{att['id']}/submit", headers=sess(att)).json()["submit_reason"] == "manual"


# ------------------------------------------------------------------ reschedule

def test_reschedule_request_then_approve_applies_the_new_window(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=2, end=6)
    assert ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "x"}).status_code == 422
    r = ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "I have an exam that day", "preferred_start": iso(30)})
    assert r.status_code == 201 and r.json()["reschedules"][0]["status"] == "pending"
    assert ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "again please"}).json()["error"]["code"] == "not_reschedulable"
    d = admin.get(f"/api/schedules/{s['id']}").json()
    assert d["pending_reschedule"] is True
    rid = d["reschedules"][0]["id"]
    new = {"action": "approve", "new_window_start": iso(30), "new_window_end": iso(34)}
    ok = admin.post(f"/api/schedules/{s['id']}/reschedule-requests/{rid}", json=new)
    assert ok.status_code == 200 and ok.json()["reschedules"][0]["status"] == "approved"
    assert abs(datetime.fromisoformat(ok.json()["window_start"]) - datetime.fromisoformat(new["new_window_start"])).total_seconds() < 1
    assert admin.post(f"/api/schedules/{s['id']}/reschedule-requests/{rid}", json=new).json()["error"]["code"] == "already_decided"
    assert any(n["type"] == "reschedule_update" for n in ap.get("/api/notifications").json()["items"])


def test_reject_needs_a_reason_and_keeps_the_original_window(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=2, end=6)
    ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "family function"})
    rid = admin.get(f"/api/schedules/{s['id']}").json()["reschedules"][0]["id"]
    assert admin.post(f"/api/schedules/{s['id']}/reschedule-requests/{rid}", json={"action": "reject"}).status_code == 422
    r = admin.post(f"/api/schedules/{s['id']}/reschedule-requests/{rid}", json={"action": "reject", "comment": "Deadline is fixed"})
    assert r.status_code == 200 and r.json()["window_start"] == s["window_start"]
    assert ap.get(f"/api/test-invitations/{s['id']}").json()["can_request_reschedule"] is True  # may ask again


def test_alternative_suggestion_can_be_accepted_or_declined(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=2, end=6)
    for accept in (False, True):
        ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "cannot make it then"})
        d = admin.get(f"/api/schedules/{s['id']}").json()
        rid = d["reschedules"][0]["id"]
        sug = {"action": "suggest", "new_window_start": iso(40), "new_window_end": iso(44), "comment": "How about this?"}
        assert admin.post(f"/api/schedules/{s['id']}/reschedule-requests/{rid}", json=sug).json()["reschedules"][0]["status"] == "alternative_suggested"
        assert ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "second request"}).status_code == 409  # one open request at a time
        r = ap.post(f"/api/test-invitations/{s['id']}/reschedule/{rid}/respond", json={"accept": accept})
        assert r.status_code == 200
        assert r.json()["reschedules"][0]["status"] == ("alternative_accepted" if accept else "alternative_declined")
    assert abs(datetime.fromisoformat(admin.get(f"/api/schedules/{s['id']}").json()["window_start"]) - datetime.fromisoformat(iso(40))).total_seconds() < 5


def test_no_reschedule_after_the_window_opens_or_once_started(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a)  # window already open
    assert ap.post(f"/api/test-invitations/{s['id']}/reschedule", json={"reason": "something came up"}).status_code == 409


# ------------------------------------------------------------------ staff management

def test_edit_changes_window_and_requires_reaccept_cancel_blocks_everything(admin):
    _, ap, a = approved_app(admin)
    publish(admin, a)
    s = make_schedule(admin, a, start=2, end=6)
    ap.post(f"/api/test-invitations/{s['id']}/accept")
    r = admin.patch(f"/api/schedules/{s['id']}", json={"window_start": iso(10), "window_end": iso(14)})
    assert r.status_code == 200 and r.json()["status"] == "invited" and r.json()["invite_link"]
    assert admin.patch(f"/api/schedules/{s['id']}", json={"window_start": iso(10), "window_end": iso(10.05)}).status_code == 422
    c = admin.post(f"/api/schedules/{s['id']}/cancel", json={"reason": "Position on hold"})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert ap.post(f"/api/test-invitations/{s['id']}/accept").status_code == 409
    assert start(ap, s).status_code == 409
    assert admin.post(f"/api/schedules/{s['id']}/cancel", json={"reason": "again"}).status_code == 409
    assert admin.patch(f"/api/schedules/{s['id']}", json={"instructions": "hi"}).status_code == 409


def test_cannot_edit_or_cancel_once_started(case):
    admin, ap, a, d, s = case
    accepted_start(ap, s)
    assert admin.patch(f"/api/schedules/{s['id']}", json={"instructions": "x"}).status_code == 409
    assert admin.post(f"/api/schedules/{s['id']}/cancel", json={"reason": "nope"}).status_code == 409
    assert admin.post(f"/api/schedules/{s['id']}/resend").status_code == 409


def test_pinned_version_is_unaffected_by_later_edits(admin):
    _, ap, a = approved_app(admin)
    d = publish(admin, a)
    s = make_schedule(admin, a)
    q = [q for sec in d["sections"] if sec["kind"] == "mcq" for q in sec["questions"]][0]
    admin.patch(f"/api/assessments/{d['id']}/questions/{q['id']}", json={"text": "A completely different question text?"})
    att = accepted_start(ap, s)
    assert "A completely different question text?" not in str(att)
    assert admin.get(f"/api/schedules/{s['id']}").json()["version"] == 1


def test_list_filters_and_audit(case):
    admin, ap, a, d, s = case
    assert admin.get("/api/schedules", params={"status": "invited"}).json()["total"] == 1
    assert admin.get("/api/schedules", params={"status": "completed"}).json()["total"] == 0
    assert admin.get("/api/schedules", params={"search": "Jane"}).json()["total"] == 1
    assert admin.get("/api/schedules", params={"application_id": a["id"] + 99}).json()["total"] == 0
    with SessionLocal() as db:
        actions = {x.action for x in db.scalars(select(AuditLog)).all()}
        assert "schedule.created" in actions
        att = db.scalars(select(TestAttempt)).first()
        assert att is None
    assert utcnow()
