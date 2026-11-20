"""Excel import into the question bank."""

import io

import pytest
from openpyxl import Workbook, load_workbook

from app.database import SessionLocal
from app.services.question_bank_service import sync_seed_bank
from tests.conftest import applicant_client, recruiter

XLSX = ("q.xlsx", None, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@pytest.fixture(autouse=True)
def seed_bank():
    with SessionLocal() as db:
        sync_seed_bank(db)
        db.commit()


def sheet(rows, headers=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(headers or ["Topic", "Question", "Option A", "Option B", "Option C", "Option D", "Option E", "Option F", "Correct answer", "Explanation", "Difficulty", "Marks"])
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(client, bank_id, data, dry_run=None, name="q.xlsx"):
    params = {} if dry_run is None else {"dry_run": str(dry_run).lower()}
    return client.post(f"/api/question-banks/{bank_id}/import", params=params, files={"file": (name, data, XLSX[2])})


@pytest.fixture
def bank(admin):
    return admin.post("/api/question-banks", json={"name": "Imported bank"}).json()["id"]


GOOD = ["Numerical ability", "What is 15 plus 27 in total?", "41", "42", "43", "44", None, None, "B", "15 + 27 = 42", "easy", 2]


def test_template_downloads_as_a_readable_workbook(admin):
    r = admin.get("/api/question-banks/import-template")
    assert r.status_code == 200 and r.content.startswith(b"PK")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb["Questions"]["A1"].value == "Topic" and "Instructions" in wb.sheetnames


def test_dry_run_saves_nothing_and_import_saves_valid_rows(admin, bank):
    data = sheet([GOOD, ["verbal", "Choose the synonym of 'rapid'.", "Slow", "Quick", "Late", None, None, None, "b", None, None, None]])
    r = upload(admin, bank, data)  # default is a dry run
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["valid"] == 2 and r.json()["imported"] == 0
    assert admin.get(f"/api/question-banks/{bank}/questions").json()["total"] == 0
    r = upload(admin, bank, data, dry_run=False)
    assert r.json()["imported"] == 2 and r.json()["failed"] == 0
    items = admin.get(f"/api/question-banks/{bank}/questions").json()["items"]
    assert {i["source"] for i in items} == {"import"} and all(i["verified_by_name"] is None for i in items)
    first = next(i for i in items if i["topic"] == "numerical")
    assert first["options"] == ["41", "42", "43", "44"] and first["correct_index"] == 1 and first["marks"] == 2 and first["difficulty"] == "easy"
    second = next(i for i in items if i["topic"] == "verbal")
    assert second["difficulty"] == "medium" and second["marks"] == 1 and second["correct_index"] == 1


def test_imported_questions_can_be_edited_afterwards(admin, bank):
    upload(admin, bank, sheet([GOOD]), dry_run=False)
    q = admin.get(f"/api/question-banks/{bank}/questions").json()["items"][0]
    r = admin.patch(f"/api/question-banks/{bank}/questions/{q['id']}", json={"text": "What is 16 plus 27 in total?", "options": ["41", "42", "43", "44"], "correct_index": 2})
    assert r.status_code == 200 and r.json()["correct_index"] == 2 and r.json()["verified_by_name"]


def test_bad_rows_are_reported_with_row_numbers_and_good_rows_still_import(admin, bank):
    rows = [
        GOOD,
        ["Cooking", "What is 1 plus 1 in total?", "1", "2", None, None, None, None, "B", None, None, None],  # topic
        ["numerical", "Too short", "1", "2", None, None, None, None, "A", None, None, None],  # text
        ["numerical", "What is 2 plus 2 in total?", "4", "4", None, None, None, None, "A", None, None, None],  # equal options
        ["numerical", "What is 3 plus 3 in total?", "5", "6", None, None, None, None, "D", None, None, None],  # key points at empty option
        ["numerical", "What is 4 plus 4 in total?", "7", None, "8", None, None, None, "C", None, None, None],  # gap
        ["numerical", "What is 5 plus 5 in total?", "9", "10", None, None, None, None, "B", None, "extreme", None],  # difficulty
        ["numerical", "What is 6 plus 6 in total?", "11", "12", None, None, None, None, "B", None, "easy", 99],  # marks
        ["numerical", "What is 7 plus 7 in total?", "13", "14", None, None, None, None, "Z", None, None, None],  # key letter
    ]
    r = upload(admin, bank, sheet(rows), dry_run=False).json()
    assert r["total_rows"] == 9 and r["imported"] == 1 and r["failed"] == 8
    assert sorted(i["row"] for i in r["issues"]) == [3, 4, 5, 6, 7, 8, 9, 10]
    assert admin.get(f"/api/question-banks/{bank}/questions").json()["total"] == 1


def test_duplicates_in_bank_or_file_are_skipped(admin, bank):
    upload(admin, bank, sheet([GOOD]), dry_run=False)
    again = [["pattern", "  WHAT is 15   plus 27 in total? ", "1", "2", None, None, None, None, "A", None, None, None], GOOD,
             ["pattern", "What comes next after 2, 4, 6, 8?", "9", "10", None, None, None, None, "B", None, None, None],
             ["pattern", "What comes next after 2, 4, 6, 8?", "9", "10", None, None, None, None, "B", None, None, None]]
    r = upload(admin, bank, sheet(again), dry_run=False).json()
    assert r["imported"] == 1 and r["duplicates"] == 3 and r["failed"] == 0


def test_bad_files_are_rejected_cleanly(admin, bank):
    assert upload(admin, bank, b"").status_code == 422
    assert upload(admin, bank, b"not a spreadsheet at all").status_code == 422
    assert upload(admin, bank, b"PK\x03\x04garbage-not-a-zip").status_code == 422
    r = upload(admin, bank, sheet([GOOD], headers=["Topic", "Question"]))
    assert r.status_code == 422 and "Missing column" in r.json()["error"]["message"]
    assert upload(admin, 99999, sheet([GOOD])).status_code == 404
    big = sheet([GOOD] * 501)
    assert upload(admin, bank, big).status_code == 422


def test_formula_and_number_cells_are_read_as_plain_values(admin, bank):
    row = ["numerical", "What is 2 to the power of 3?", 6, 8, 9, 12, None, None, "B", "=1+1", None, 1]
    r = upload(admin, bank, sheet([row]), dry_run=False).json()
    assert r["imported"] == 1
    q = admin.get(f"/api/question-banks/{bank}/questions").json()["items"][0]
    assert q["options"] == ["6", "8", "9", "12"]


def test_permissions_and_audit(admin, bank):
    data = sheet([GOOD])
    other = recruiter(admin, "oth2@solidpro-test.com", perms=("review_applications",))
    assert upload(other, bank, data).status_code == 403
    viewer = recruiter(admin, "view2@solidpro-test.com", perms=("generate_assessments",))
    assert upload(viewer, bank, data).status_code == 403 and viewer.get("/api/question-banks/import-template").status_code == 403
    mgr = recruiter(admin, "mgr2@solidpro-test.com", perms=("manage_question_bank",))
    assert upload(mgr, bank, data, dry_run=False).json()["imported"] == 1
    ap = applicant_client("cand-import@gmail.com")
    assert upload(ap, bank, data).status_code == 404
    from sqlalchemy import select

    from app.models import AuditLog

    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "question_bank.imported")) is not None
