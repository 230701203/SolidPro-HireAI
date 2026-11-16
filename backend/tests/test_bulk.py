"""Bulk resume screening (Phase 7)."""

import io

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, BulkItem, CandidateProfile, JobApplication, User
from app.services import bulk_service, export_service, resume_extract
from tests.conftest import applicant_client, make_docx, make_opening, make_pdf, recruiter, user_id

RESUME = (
    "Priya Raman\npriya.raman@example.org\n+91 98765 43210\n\nSummary: 4 years of experience building Python and FastAPI services.\n"
    "Skills: Python, FastAPI, PostgreSQL, Docker\nEducation\nB.E. Computer Science, Anna University 2022\n"
    + "Worked on backend APIs and data pipelines. " * 8
)


def _files(*items):
    return [("files", (n, io.BytesIO(d), "application/octet-stream")) for n, d in items]


def _upload(c, opening_id, *items, name="Campus drive"):
    return c.post("/api/bulk-batches", data={"opening_id": str(opening_id), "name": name}, files=_files(*items))


@pytest.fixture
def opening(admin):
    return make_opening(admin)


# ---- extraction unit tests ----------------------------------------------------------------------

def test_extraction_finds_fields_and_warns_on_gaps():
    ex = resume_extract.extract(RESUME, ["FastAPI"])
    assert ex.email == "priya.raman@example.org"
    assert ex.candidate_name == "Priya Raman"
    assert ex.experience_years == 4.0
    assert {"Python", "FastAPI", "PostgreSQL"} <= set(ex.skills)
    assert any("B.E." in e for e in ex.education)
    empty = resume_extract.extract("hello")
    assert empty.email is None and empty.warnings


def test_skill_match_uses_word_boundaries():
    assert "go" not in [s.lower() for s in resume_extract.extract("I like going to gold mines " * 20).skills]


# ---- upload and processing ----------------------------------------------------------------------

def test_upload_processes_files_and_labels_mock_ai(admin, opening):
    r = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME)), ("b.docx", make_docx(RESUME.replace("Priya Raman", "Karan Shah").replace("priya.raman", "karan.s"))))
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["batch"]["ai_is_mock"] is True and body["rejected"] == []
    bid = body["batch"]["id"]
    # background task has run (TestClient executes it before returning)
    p = admin.get(f"/api/bulk-batches/{bid}").json()["progress"]
    assert p["done"] == 2 and p["complete"] is True
    items = admin.get(f"/api/bulk-batches/{bid}/items").json()["items"]
    assert len(items) == 2 and all(i["match_score"] is not None for i in items)
    assert items[0]["match_score"] >= items[1]["match_score"]  # default sort: score desc
    # nothing about applicants changed
    with SessionLocal() as db:
        assert db.scalar(select(JobApplication.id)) is None
        assert db.scalars(select(User).where(User.email.like("%example.org"))).first() is None


def test_invalid_files_are_rejected_with_reasons_and_valid_ones_kept(admin, opening):
    r = _upload(admin, opening["id"], ("good.pdf", make_pdf(RESUME)), ("evil.pdf", b"MZ not a pdf"), ("note.txt", b"hi"), ("empty.pdf", b""))
    assert r.status_code == 202
    reasons = {x["filename"]: x["reason"] for x in r.json()["rejected"]}
    assert set(reasons) == {"evil.pdf", "note.txt", "empty.pdf"}
    assert r.json()["batch"]["progress"]["total"] == 1


def test_oversized_and_all_invalid_batches(admin, opening):
    big = b"%PDF-" + b"0" * (2 * 1024 * 1024)
    r = _upload(admin, opening["id"], ("big.pdf", big))
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_valid_files"


def test_max_files_per_batch(admin, opening, monkeypatch):
    monkeypatch.setenv("BULK_MAX_FILES", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        r = _upload(admin, opening["id"], *[(f"{i}.pdf", make_pdf(RESUME)) for i in range(3)])
        assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_files"
    finally:
        monkeypatch.delenv("BULK_MAX_FILES")
        get_settings.cache_clear()


def test_corrupt_file_fails_alone_and_can_be_retried(admin, opening):
    corrupt = b"%PDF-1.4 this is not really a pdf body"
    r = _upload(admin, opening["id"], ("ok.pdf", make_pdf(RESUME)), ("broken.pdf", corrupt))
    bid = r.json()["batch"]["id"]
    p = admin.get(f"/api/bulk-batches/{bid}").json()["progress"]
    assert p["done"] == 1 and p["failed"] == 1 and p["complete"] is True
    failed = admin.get(f"/api/bulk-batches/{bid}/items", params={"status": "failed"}).json()["items"]
    assert failed[0]["filename"] == "broken.pdf" and failed[0]["error"]
    assert admin.post(f"/api/bulk-batches/{bid}/retry").json()["requeued"] == 1


def test_duplicates_in_batch_by_file_and_email_and_existing_applicant(admin, opening):
    applicant_client("priya.raman@example.org")  # registered applicant with the same email as the resume
    same = make_pdf(RESUME)
    other_same_email = make_pdf(RESUME + " extra line to change the hash")
    r = _upload(admin, opening["id"], ("1.pdf", same), ("2.pdf", same), ("3.pdf", other_same_email))
    bid = r.json()["batch"]["id"]
    items = {i["filename"]: i for i in admin.get(f"/api/bulk-batches/{bid}/items").json()["items"]}
    assert items["1.pdf"]["duplicate_kind"] == "existing_applicant" and items["1.pdf"]["existing_applicant"] is True
    assert items["2.pdf"]["duplicate_kind"] == "duplicate_file"
    assert items["3.pdf"]["duplicate_kind"] == "duplicate_in_batch"
    assert items["1.pdf"]["existing_application_id"] is None  # they have not applied to this opening
    only_dupes = admin.get(f"/api/bulk-batches/{bid}/items", params={"duplicates": "true"}).json()
    assert only_dupes["total"] == 3


def test_filters_sort_search_and_pagination(admin, opening):
    files = [(f"r{i}.pdf", make_pdf(RESUME.replace("priya.raman", f"p{i}").replace("Priya Raman", f"Person {'ABCDE'[i]}"))) for i in range(5)]
    bid = _upload(admin, opening["id"], *files).json()["batch"]["id"]
    page = admin.get(f"/api/bulk-batches/{bid}/items", params={"page_size": 2, "sort": "name", "desc": "false"}).json()
    assert page["total"] == 5 and page["pages"] == 3 and len(page["items"]) == 2
    assert admin.get(f"/api/bulk-batches/{bid}/items", params={"search": "p3@"}).json()["total"] == 1
    assert admin.get(f"/api/bulk-batches/{bid}/items", params={"min_score": 101}).status_code == 422
    assert admin.get(f"/api/bulk-batches/{bid}/items", params={"sort": "bogus"}).status_code == 422


def test_triage_is_audited_and_changes_no_application(admin, opening):
    bid = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME))).json()["batch"]["id"]
    iid = admin.get(f"/api/bulk-batches/{bid}/items").json()["items"][0]["id"]
    r = admin.put(f"/api/bulk-items/{iid}/triage", json={"status": "not_suitable", "note": "Looking for more experience"})
    assert r.status_code == 200 and r.json()["review_status"] == "not_suitable"
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "bulk_item.triage")) is not None
        assert db.scalar(select(JobApplication.id)) is None
    assert admin.put(f"/api/bulk-items/{iid}/triage", json={"status": "selected"}).status_code == 422


def test_download_is_authorised_and_audited_and_delete_removes_files(admin, opening):
    bid = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME))).json()["batch"]["id"]
    item = admin.get(f"/api/bulk-batches/{bid}/items").json()["items"][0]
    r = admin.get(f"/api/bulk-items/{item['id']}/file")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "no-store" in r.headers["cache-control"]
    with SessionLocal() as db:
        stored = db.scalar(select(BulkItem.stored_name))
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "bulk_item.download")) is not None
    from app.services import storage_service

    assert storage_service.path_for(stored).exists()
    assert admin.delete(f"/api/bulk-batches/{bid}").status_code == 204
    assert not storage_service.path_for(stored).exists()
    assert admin.get(f"/api/bulk-batches/{bid}").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(BulkItem.id)) is None


# ---- access control -----------------------------------------------------------------------------

def test_permission_and_assignment_are_enforced(admin, opening):
    bid = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME))).json()["batch"]["id"]
    iid = admin.get(f"/api/bulk-batches/{bid}/items").json()["items"][0]["id"]

    no_perm = recruiter(admin, "np@solidpro-test.com", perms=("review_applications",))
    admin.patch(f"/api/job-openings/{opening['id']}", json={"assigned_employee_ids": [user_id(no_perm)]})
    assert no_perm.get("/api/bulk-batches").status_code == 403
    assert _upload(no_perm, opening["id"], ("a.pdf", make_pdf(RESUME))).status_code == 403

    bulk = recruiter(admin, "bk@solidpro-test.com", perms=("bulk_upload_resumes",))
    assert bulk.get(f"/api/bulk-batches/{bid}").status_code == 404  # not assigned: existence hidden
    assert bulk.get(f"/api/bulk-items/{iid}").status_code == 404
    assert bulk.get(f"/api/bulk-items/{iid}/file").status_code == 404
    assert _upload(bulk, opening["id"], ("a.pdf", make_pdf(RESUME))).status_code == 404
    assert bulk.get("/api/bulk-batches").json()["total"] == 0
    admin.patch(f"/api/job-openings/{opening['id']}", json={"assigned_employee_ids": [user_id(no_perm), user_id(bulk)]})
    assert bulk.get(f"/api/bulk-batches/{bid}").status_code == 200
    assert bulk.get("/api/bulk-batches").json()["total"] == 1
    assert _upload(bulk, opening["id"], ("b.pdf", make_pdf(RESUME))).status_code == 202


def test_applicants_and_anonymous_are_locked_out(admin, opening, client):
    ap = applicant_client("x@gmail.com")
    assert ap.get("/api/bulk-batches").status_code == 404
    assert _upload(ap, opening["id"], ("a.pdf", make_pdf(RESUME))).status_code == 404
    assert client.get("/api/bulk-batches").status_code == 401
    assert client.get("/api/bulk-items/1/file").status_code == 401


# ---- export and CSV injection ------------------------------------------------------------------

def test_export_neutralises_formula_injection(admin, opening):
    evil = "=HYPERLINK(\"http://evil\",\"x\")\nevil@example.org\n" + "Python developer. " * 30
    bid = _upload(admin, opening["id"], ("=cmd.pdf", make_pdf(evil))).json()["batch"]["id"]
    csv_body = admin.get(f"/api/bulk-batches/{bid}/export").content.decode("utf-8-sig")
    for line in csv_body.splitlines()[1:]:
        for cell in line.split(","):
            assert not cell.startswith(("=", "+", "@")), cell
    x = admin.get(f"/api/bulk-batches/{bid}/export", params={"format": "xlsx"})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(x.content)).active
    assert all(not str(c.value or "").startswith(("=", "+", "@")) for row in ws.iter_rows(min_row=2) for c in row)
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "bulk_batch.export")) is not None


def test_safe_cell_unit():
    assert export_service.safe_cell("=1+1") == "'=1+1"
    assert export_service.safe_cell("-2+3") == "'-2+3"
    assert export_service.safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert export_service.safe_cell("normal") == "normal"
    assert export_service.safe_cell(["a", "=b"]) == "a, =b"
    assert export_service.safe_cell(3) == 3


# ---- sweeper recovery ---------------------------------------------------------------------------

def test_sweeper_recovers_stuck_items(admin, opening):
    from datetime import timedelta

    from app.models import BulkItemStatus
    from app.models.base import utcnow

    bid = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME))).json()["batch"]["id"]
    with SessionLocal() as db:
        it = db.scalar(select(BulkItem))
        it.status = BulkItemStatus.PROCESSING
        it.match_score = None
        db.commit()
        db.execute(BulkItem.__table__.update().values(updated_at=utcnow() - timedelta(minutes=30)))
        db.commit()
        result = bulk_service.sweep(db)
    assert result["bulk_recovered"] == 1 and result["bulk_processed"] == 1
    assert admin.get(f"/api/bulk-batches/{bid}").json()["progress"]["done"] == 1


def test_provider_unavailable_returns_503_and_creates_nothing(admin, opening, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    try:
        r = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME)))
        assert r.status_code == 503
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    with SessionLocal() as db:
        assert db.scalar(select(CandidateProfile.id)) is None
        assert db.scalar(select(BulkItem.id)) is None


def test_uploader_is_notified_once_when_batch_finishes_and_others_are_not(admin, opening):
    from app.models import Notification

    other = recruiter(admin, "other@solidpro-test.com", perms=("bulk_upload_resumes",))
    admin.patch(f"/api/job-openings/{opening['id']}", json={"assigned_employee_ids": [user_id(other)]})
    bid = _upload(admin, opening["id"], ("a.pdf", make_pdf(RESUME)), ("bad.pdf", b"%PDF-1.4 not really a pdf")).json()["batch"]["id"]
    with SessionLocal() as db:
        notes = db.scalars(select(Notification).where(Notification.type == "bulk_batch_complete")).all()
        assert len(notes) == 1
        assert notes[0].user_id == user_id(admin) and notes[0].link == f"/bulk/{bid}"
        assert "1 of 2" in notes[0].message and "1 failed" in notes[0].message
        assert db.scalar(select(Notification.id).where(Notification.user_id == user_id(other), Notification.type == "bulk_batch_complete")) is None
