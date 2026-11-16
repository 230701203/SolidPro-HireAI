import os
from datetime import date, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, EmailLog
from tests.conftest import (
    PROFILE,
    applicant_client,
    approved_employee,
    login,
    make_blank_pdf,
    make_docx,
    make_opening,
    make_pdf,
    new_client,
    recruiter,
    register,
    user_id,
    verify,
)


def _upload(c, name, data, ctype="application/octet-stream"):
    return c.post("/api/applicants/resumes", files={"file": (name, data, ctype)})


# ------------------------------------------------------------------ profile


def test_profile_save_completion_and_validation():
    c = applicant_client("p@gmail.com", complete=False, resume=False)
    p = c.get("/api/applicants/profile").json()
    assert p["completion"] < 20 and "Uploaded resume" in p["missing"]

    assert c.put("/api/applicants/profile", json={**PROFILE, "linkedin_url": "linkedin.com/in/x"}).status_code == 422
    assert c.put("/api/applicants/profile", json={**PROFILE, "date_of_birth": "2999-01-01"}).status_code == 422
    assert c.put("/api/applicants/profile", json={**PROFILE, "total_experience_years": -1}).status_code == 422
    bad = {**PROFILE, "experience": [{"kind": "job", "title": "Dev", "start_date": "2024-05-01", "end_date": "2023-01-01"}]}
    assert c.put("/api/applicants/profile", json=bad).status_code == 422

    body = {**PROFILE, "skills": [{"name": "Python", "kind": "technical"}, {"name": "python", "kind": "technical"}, {"name": "Python", "kind": "tool"}]}
    p = c.put("/api/applicants/profile", json=body).json()
    assert len([s for s in p["skills"] if s["kind"] == "technical"]) == 1  # case-insensitive de-dupe per kind
    assert p["education"][0]["institution"] == "Rajalakshmi Engineering College"
    assert p["completion"] == 89 and p["missing"] == ["Uploaded resume"]

    # Replacing lists really replaces them.
    p = c.put("/api/applicants/profile", json={**PROFILE, "education": []}).json()
    assert p["education"] == []

    assert c.get("/api/applicants/profile").status_code == 200


def test_profile_endpoints_are_applicant_only(admin):
    rec = recruiter(admin)
    assert rec.get("/api/applicants/profile").status_code == 403
    assert admin.put("/api/applicants/profile", json=PROFILE).status_code == 403
    assert new_client().get("/api/applicants/profile").status_code == 401


# ------------------------------------------------------------------ resume upload & validation


def test_resume_versions_pdf_and_docx_and_no_path_leak():
    c = applicant_client("r@gmail.com", complete=False, resume=False)
    r1 = _upload(c, "../../etc/my cv.pdf", make_pdf())
    assert r1.status_code == 201
    j1 = r1.json()
    assert j1["version"] == 1 and j1["original_filename"] == "my cv.pdf"  # path components stripped
    assert "stored_name" not in j1 and "path" not in str(j1).lower()
    r2 = _upload(c, "cv v2.docx", make_docx("Jane Doe. Python, FastAPI, PostgreSQL."))
    assert r2.status_code == 201 and r2.json()["version"] == 2
    listed = c.get("/api/applicants/resumes").json()
    assert [r["version"] for r in listed] == [2, 1] and listed[0]["is_current"] and not listed[1]["is_current"]  # history is kept
    assert "my cv.pdf" in [r["original_filename"] for r in listed]


def test_resume_validation_rejects_bad_files():
    c = applicant_client("v@gmail.com", complete=False, resume=False)
    cases = {
        "wrong extension": ("notes.txt", b"hello world", 415),
        "executable renamed to pdf": ("evil.pdf", b"MZ\x90\x00 this is an exe", 422),
        "empty file": ("empty.pdf", b"", 422),
        "pdf magic but garbage": ("broken.pdf", b"%PDF-1.7\nnot really a pdf at all", 422),
        "corrupt docx": ("broken.docx", b"PK\x03\x04garbage", 422),
        "docx without word part": ("zip.docx", _zip_without_word(), 422),
        "blank pdf (no text)": ("blank.pdf", make_blank_pdf(), 422),
        "oversized": ("big.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10), 413),
    }
    for label, (name, data, code) in cases.items():
        r = _upload(c, name, data)
        assert r.status_code == code, f"{label}: {r.status_code} {r.text}"
        assert r.json()["error"]["code"] == "invalid_file", label
    assert c.get("/api/applicants/resumes").json() == []  # nothing was stored
    stored = [f for f in os.listdir(os.environ["UPLOAD_DIR"])] if os.path.isdir(os.environ["UPLOAD_DIR"]) else []
    assert all(not f.endswith(".part") for f in stored)


def _zip_without_word() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    return buf.getvalue()


def test_resume_download_access_control(admin):
    rec = recruiter(admin, "assigned@solidpro-test.com")
    outsider = recruiter(admin, "outsider@solidpro-test.com")
    no_perm = approved_employee(admin, "noperm@solidpro-test.com", ("manage_job_openings",))
    o = make_opening(rec)
    owner = applicant_client("owner@gmail.com")
    stranger = applicant_client("stranger@gmail.com")
    rid = owner.get("/api/applicants/resumes").json()[0]["id"]
    url = f"/api/resumes/{rid}/file"

    assert owner.get(url).status_code == 200
    assert stranger.get(url).status_code == 404
    assert new_client().get(url).status_code == 401
    assert rec.get(url).status_code == 404  # no application yet -> recruiters cannot see the file
    assert admin.get(url).status_code == 200

    assert owner.post("/api/applications", json={"opening_id": o["id"]}).status_code == 201
    r = rec.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline") and r.headers["x-content-type-options"] == "nosniff"
    assert r.content.startswith(b"%PDF-")
    assert rec.get(url, params={"download": True}).headers["content-disposition"].startswith("attachment")
    assert outsider.get(url).status_code == 404  # not assigned to that opening
    assert no_perm.get(url).status_code == 404  # assigned/created but lacks review_applications
    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.action == "resume.downloaded")).first()


# ------------------------------------------------------------------ applying


def test_apply_requires_complete_profile_and_prevents_duplicates(admin):
    o = make_opening(admin)
    bare = applicant_client("bare@gmail.com", complete=False, resume=False)
    r = bare.post("/api/applications", json={"opening_id": o["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "profile_incomplete"
    assert "resume" in r.json()["error"]["message"] and "education" in r.json()["error"]["message"]

    ap = applicant_client("ok@gmail.com")
    r = ap.post("/api/applications", json={"opening_id": o["id"], "cover_note": "Excited to join"})
    assert r.status_code == 201
    a = r.json()
    assert a["status"] == "submitted" and a["resume"]["version"] == 1 and a["cover_note"] == "Excited to join"
    assert a["candidate"] is None  # applicants never receive the staff view
    dup = ap.post("/api/applications", json={"opening_id": o["id"]})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_applied"

    assert ap.get(f"/api/jobs/{o['id']}").json()["applied"] is True


def test_apply_to_unavailable_openings(admin):
    ap = applicant_client("na@gmail.com")
    draft = make_opening(admin, publish=False)
    assert ap.post("/api/applications", json={"opening_id": draft["id"]}).status_code == 404
    assert ap.post("/api/applications", json={"opening_id": 99999}).status_code == 404
    closed = make_opening(admin)
    admin.post(f"/api/job-openings/{closed['id']}/close")
    r = ap.post("/api/applications", json={"opening_id": closed["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "applications_closed"
    expired = make_opening(admin)
    admin.patch(f"/api/job-openings/{expired['id']}", json={"deadline": (date.today() - timedelta(days=1)).isoformat()})
    assert ap.post("/api/applications", json={"opening_id": expired["id"]}).status_code == 409


def test_one_account_many_applications_and_resume_version_is_pinned(admin):
    o1, o2 = make_opening(admin, title="Job One"), make_opening(admin, title="Job Two")
    ap = applicant_client("multi@gmail.com")
    a1 = ap.post("/api/applications", json={"opening_id": o1["id"]}).json()
    _upload(ap, "newer.docx", make_docx("Updated resume with more detail."))
    a2 = ap.post("/api/applications", json={"opening_id": o2["id"]}).json()
    assert a1["resume"]["version"] == 1 and a2["resume"]["version"] == 2  # each keeps the exact version used
    assert ap.get(f"/api/applications/{a1['id']}").json()["resume"]["version"] == 1

    mine = ap.get("/api/applications").json()
    assert mine["total"] == 2
    with SessionLocal() as db:
        from app.models import CandidateProfile

        assert len(db.scalars(select(CandidateProfile)).all()) == 1  # still one candidate record

    other = applicant_client("other@gmail.com")
    rid = ap.get("/api/applicants/resumes").json()[1]["id"]
    r = other.post("/api/applications", json={"opening_id": o1["id"], "resume_id": rid})
    assert r.status_code == 422  # cannot attach someone else's resume


# ------------------------------------------------------------------ review workflow


def _setup(admin, perms=("manage_job_openings", "review_applications")):
    rec = recruiter(admin, "rec@solidpro-test.com", perms)
    o = make_opening(rec, title="Reviewed Role")
    ap = applicant_client("cand@gmail.com")
    a = ap.post("/api/applications", json={"opening_id": o["id"]}).json()
    return rec, o, ap, a


def test_review_flow_with_visibility_rules(admin):
    rec, o, ap, a = _setup(admin)
    aid = a["id"]

    # Reviewer was notified of the new application.
    assert any(n["type"] == "application_submitted" for n in rec.get("/api/notifications").json()["items"])

    lst = rec.get("/api/applications").json()
    assert lst["total"] == 1 and lst["items"][0]["candidate_name"] == "Jane Doe"
    d = rec.get(f"/api/applications/{aid}").json()
    assert d["can_review"] is True and d["candidate"]["email"] == "cand@gmail.com" and d["candidate"]["education"]

    assert rec.post(f"/api/applications/{aid}/start-review").json()["status"] == "under_review"
    assert rec.post(f"/api/applications/{aid}/start-review").status_code == 409

    # Internal comment: recorded, but invisible to the applicant.
    assert rec.post(f"/api/applications/{aid}/comment", json={"message": "Strong projects, check Python depth"}).status_code == 200
    assert rec.post(f"/api/applications/{aid}/comment", json={"message": "  "}).status_code == 422
    mine = ap.get(f"/api/applications/{aid}").json()
    assert "Strong projects" not in str(mine) and mine["candidate"] is None
    assert "Strong projects" in str(rec.get(f"/api/applications/{aid}/history").json())
    assert "Emp Loyee" not in str(mine) and "rec@solidpro-test.com" not in str(mine)  # reviewer identity hidden from applicant
    assert {h["actor_name"] for h in mine["history"]} <= {"Jane Doe", "Recruitment team"}

    # Request more info.
    assert rec.post(f"/api/applications/{aid}/request-info", json={"message": "x"}).status_code == 422
    r = rec.post(f"/api/applications/{aid}/request-info", json={"message": "Please add your GitHub link"})
    assert r.json()["status"] == "info_requested"
    assert any(n["type"] == "application_info_requested" for n in ap.get("/api/notifications").json()["items"])
    assert any("GitHub link" in (h["comment"] or "") for h in ap.get(f"/api/applications/{aid}").json()["history"])

    # Applicant replies (optionally with a new resume) -> back to review.
    assert ap.post(f"/api/applications/{aid}/respond", json={"message": "Added to my profile"}).json()["status"] == "under_review"
    assert ap.post(f"/api/applications/{aid}/respond", json={"message": "again again"}).status_code == 409
    assert any(n["type"] == "application_info_provided" for n in rec.get("/api/notifications").json()["items"])

    # Approve (final).
    r = rec.post(f"/api/applications/{aid}/approve", json={"note": "Welcome to the next stage"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_by_name"] == "Emp Loyee"
    assert ap.get(f"/api/applications/{aid}").json()["decided_by_name"] == "Recruitment team"
    for path, body in [("approve", {}), ("reject", {"reason": "changed my mind"}), ("request-info", {"message": "more please"}), ("start-review", None)]:
        assert rec.post(f"/api/applications/{aid}/{path}", json=body).status_code == 409, path  # decisions are final
    assert ap.post(f"/api/applications/{aid}/withdraw").status_code == 409

    with SessionLocal() as db:
        templates = {e.template for e in db.scalars(select(EmailLog).where(EmailLog.to_email == "cand@gmail.com")).all()}
        actions = {x.action for x in db.scalars(select(AuditLog)).all()}
    assert {"application_submitted", "application_info_requested", "application_approved"} <= templates
    assert {"application.submitted", "application.approved", "application.commented", "application.info_requested", "application.review_started"} <= actions
    assert any(n["type"] == "application_approved" for n in ap.get("/api/notifications").json()["items"])


def test_reject_requires_reason_and_notifies_applicant(admin):
    rec, o, ap, a = _setup(admin)
    assert rec.post(f"/api/applications/{a['id']}/reject", json={"reason": ""}).status_code == 422
    r = rec.post(f"/api/applications/{a['id']}/reject", json={"reason": "Requires 3+ years experience"})
    assert r.json()["status"] == "rejected"
    d = ap.get(f"/api/applications/{a['id']}").json()
    assert d["status"] == "rejected" and d["decision_reason"] == "Requires 3+ years experience"
    with SessionLocal() as db:
        assert db.scalar(select(EmailLog).where(EmailLog.template == "application_rejected"))


def test_ai_free_rule_no_automatic_decisions(admin):
    """A fresh application must wait for a human: nothing moves it automatically."""
    rec, o, ap, a = _setup(admin)
    assert ap.get(f"/api/applications/{a['id']}").json()["status"] == "submitted"
    assert rec.get(f"/api/applications/{a['id']}").json()["status"] == "submitted"


def test_withdraw(admin):
    rec, o, ap, a = _setup(admin)
    assert ap.post(f"/api/applications/{a['id']}/withdraw").json()["status"] == "withdrawn"
    assert rec.post(f"/api/applications/{a['id']}/approve", json={}).status_code == 409
    assert any(n["type"] == "application_withdrawn" for n in rec.get("/api/notifications").json()["items"])
    assert ap.post("/api/applications", json={"opening_id": o["id"]}).status_code == 409  # still one application per opening


def test_access_scoping_for_reviewers_and_applicants(admin):
    rec, o, ap, a = _setup(admin)
    aid = a["id"]
    outsider = recruiter(admin, "out@solidpro-test.com")  # perms but not assigned
    no_review = approved_employee(admin, "nr@solidpro-test.com", ("manage_job_openings",))
    stranger = applicant_client("stranger@gmail.com")

    assert outsider.get(f"/api/applications/{aid}").status_code == 404
    assert outsider.get("/api/applications").json()["total"] == 0
    assert outsider.post(f"/api/applications/{aid}/approve", json={}).status_code == 404
    assert outsider.get(f"/api/job-openings/{o['id']}/applications").status_code == 404
    assert no_review.get("/api/applications").status_code == 403
    assert no_review.get("/api/applicants").status_code == 403
    assert stranger.get(f"/api/applications/{aid}").status_code == 404
    assert stranger.post(f"/api/applications/{aid}/withdraw").status_code == 404
    assert stranger.post(f"/api/applications/{aid}/respond", json={"message": "hacking"}).status_code == 404
    assert stranger.get("/api/applications").json()["total"] == 0
    assert ap.post(f"/api/applications/{aid}/approve", json={}).status_code == 403  # applicants cannot review
    assert ap.get("/api/applicants").status_code == 403
    assert new_client().get(f"/api/applications/{aid}").status_code == 401

    # Admin can override assignments and sees everything.
    assert admin.get(f"/api/applications/{aid}").status_code == 200
    assert admin.get(f"/api/job-openings/{o['id']}/applications").json()["total"] == 1

    # Moving the assignment moves access.
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(outsider)]})
    assert rec.get(f"/api/applications/{aid}").status_code == 404
    assert outsider.get(f"/api/applications/{aid}").status_code == 200


def test_applicant_directory_is_scoped(admin):
    rec, o, ap, a = _setup(admin)
    applicant_client("nobody@gmail.com")  # registered, never applied to rec's opening
    listing = rec.get("/api/applicants").json()
    assert [x["email"] for x in listing["items"]] == ["cand@gmail.com"] and listing["items"][0]["applications_count"] == 1
    assert admin.get("/api/applicants").json()["total"] == 2
    assert admin.get("/api/applicants", params={"search": "nobody"}).json()["total"] == 1

    cid = listing["items"][0]["candidate_id"]
    assert rec.get(f"/api/applicants/{cid}").status_code == 200
    other_cid = next(x["candidate_id"] for x in admin.get("/api/applicants").json()["items"] if x["email"] == "nobody@gmail.com")
    assert rec.get(f"/api/applicants/{other_cid}").status_code == 404
    assert rec.get("/api/applicants/999999").status_code == 404
    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.action == "applicant.viewed")).first()  # access to personal data is audited


def test_dashboards_reflect_real_data(admin):
    rec, o, ap, a = _setup(admin)
    d = admin.get("/api/dashboard/summary").json()["cards"]
    assert d["total_openings"] == 1 and d["active_openings"] == 1 and d["total_applications"] == 1 and d["pending_application_reviews"] == 1
    s = rec.get("/api/dashboard/summary").json()["stats"]
    assert s == {"assigned_openings": 1, "assigned_applicants": 1, "pending_reviews": 1, "approved": 0, "shortlisted": 0}
    s = ap.get("/api/dashboard/summary").json()
    assert s["stats"] == {"total_applications": 1, "under_review": 1, "approved": 0, "shortlisted": 0, "rejected": 0} and s["profile_completion"] == 100
    rec.post(f"/api/applications/{a['id']}/approve", json={})
    assert admin.get("/api/dashboard/summary").json()["cards"]["pending_application_reviews"] == 0
    assert ap.get("/api/dashboard/summary").json()["stats"]["approved"] == 1


def test_registration_still_blocks_unverified_applicants_from_applying(admin):
    o = make_opening(admin)
    c = new_client()
    register(c, "unverified@gmail.com")
    assert login(c, "unverified@gmail.com").status_code == 403
    assert c.post("/api/applications", json={"opening_id": o["id"]}).status_code == 401
    verify(c, "unverified@gmail.com")
