"""Import aptitude questions into a bank from an Excel (.xlsx) file.

Every row is checked with the same rules as adding a question by hand. A dry run reports what would happen without
saving anything; the real import saves all valid rows and reports the rest. Imported questions are marked
source="import" and unverified, so a person still has to check the answer keys (editing a question marks it verified).
"""

import io
import re
import zipfile

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import BankQuestion, QuestionBank, User
from app.schemas.assessment import BankQuestionIn, ImportResult, ImportRowIssue
from app.services import audit_service

MAX_ROWS = 500
MAX_UNZIPPED = 30 * 1024 * 1024
LETTERS = "ABCDEF"
SHEET = "Questions"
HEADERS = ["Topic", "Question", "Option A", "Option B", "Option C", "Option D", "Option E", "Option F", "Correct answer", "Explanation", "Difficulty", "Marks"]
TOPIC_LABELS = {
    "numerical": "Numerical ability", "logical": "Logical reasoning", "analytical": "Analytical reasoning",
    "verbal": "Verbal ability", "data_interpretation": "Data interpretation", "pattern": "Pattern recognition",
}
TOPIC_LOOKUP = {**{k: k for k in TOPIC_LABELS}, **{v.lower(): k for k, v in TOPIC_LABELS.items()}}
FIELD_NAMES = {"topic": "Topic", "text": "Question", "options": "Options", "correct_index": "Correct answer", "explanation": "Explanation", "difficulty": "Difficulty", "marks": "Marks"}


def template_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADERS)
    widths = [22, 60, 24, 24, 24, 24, 20, 20, 16, 40, 12, 8]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    for col, formula in (("A", '"' + ",".join(TOPIC_LABELS.values()) + '"'), ("I", '"A,B,C,D,E,F"'), ("K", '"easy,medium,hard"')):
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{MAX_ROWS + 1}")
    info = wb.create_sheet("Instructions")
    for line in (
        ["How to fill in the Questions sheet"],
        ["One question per row, starting on row 2. Do not rename or reorder the header row."],
        ["Topic: one of " + ", ".join(TOPIC_LABELS.values()) + "."],
        ["Question: at least 10 characters."],
        ["Option A to Option F: provide at least two options (A and B). Leave unused options empty. Options must be different."],
        ["Correct answer: the letter of the right option (A to F)."],
        ["Explanation: optional."],
        ["Difficulty: easy, medium or hard. Empty means medium."],
        ["Marks: a whole number from 1 to 10. Empty means 1."],
        [f"Up to {MAX_ROWS} rows per file. Questions already in the bank (same text) are skipped."],
        ["Imported questions are marked unverified. Please check each answer key, and edit any question later from the bank."],
        [],
        ["Example row"],
        ["Numerical ability", "A train travels 120 km in 2 hours. What is its speed?", "40 km/h", "60 km/h", "80 km/h", "100 km/h", "", "", "B", "Speed = distance / time = 120 / 2 = 60 km/h.", "easy", 1],
    ):
        info.append(line)
    info.column_dimensions["A"].width = 110
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _read_rows(data: bytes) -> list[tuple[int, dict[str, str]]]:
    limit = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise AppError(422, "validation_error", "The file is empty.")
    if len(data) > limit:
        raise AppError(413, "file_too_large", f"The file is larger than {get_settings().max_upload_mb} MB.")
    if not data.startswith(b"PK"):
        raise AppError(422, "validation_error", "Upload an Excel .xlsx file (use the template). Older .xls files are not supported.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise AppError(422, "validation_error", "The spreadsheet is too large to read.")
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except AppError:
        raise
    except Exception:
        raise AppError(422, "validation_error", "This file could not be read as an Excel .xlsx workbook.") from None
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise AppError(422, "validation_error", "The sheet is empty. Use the template.")
    names = [_cell(h).lower() for h in header]
    missing = [h for h in ("Topic", "Question", "Option A", "Option B", "Correct answer") if h.lower() not in names]
    if missing:
        raise AppError(422, "validation_error", "Missing column(s): " + ", ".join(missing) + ". Use the template.")
    idx = {n: i for i, n in enumerate(names) if n}
    out: list[tuple[int, dict[str, str]]] = []
    for n, row in enumerate(rows, start=2):
        rec = {h: _cell(row[idx[h.lower()]]) if idx.get(h.lower()) is not None and idx[h.lower()] < len(row) else "" for h in HEADERS}
        if not any(rec.values()):
            continue
        out.append((n, rec))
        if len(out) > MAX_ROWS:
            raise AppError(422, "validation_error", f"The file has more than {MAX_ROWS} questions. Split it into smaller files.")
    wb.close()
    return out


def _parse(rec: dict[str, str]) -> BankQuestionIn:
    problems: list[str] = []
    topic = TOPIC_LOOKUP.get(rec["Topic"].lower().replace(" ", "_")) or TOPIC_LOOKUP.get(rec["Topic"].lower())
    if topic is None:
        problems.append("Topic must be one of: " + ", ".join(TOPIC_LABELS.values()))
    options = [rec[f"Option {c}"] for c in LETTERS]
    while options and not options[-1]:
        options.pop()
    if any(not o for o in options):
        problems.append("Options must be filled in order (no gaps between Option A and the last option)")
    ans = rec["Correct answer"].strip().upper()
    ci = LETTERS.index(ans) if len(ans) == 1 and ans in LETTERS else None
    if ci is None:
        problems.append("Correct answer must be a letter from A to F")
    elif ci >= len(options) or not options[ci]:
        problems.append(f"Correct answer {ans} points to an empty option")
    difficulty = rec["Difficulty"].lower() or "medium"
    marks_raw = rec["Marks"] or "1"
    try:
        marks = int(float(marks_raw))
    except ValueError:
        problems.append("Marks must be a whole number from 1 to 10")
        marks = 1
    if problems:
        raise ValueError("; ".join(problems))
    try:
        return BankQuestionIn(topic=topic, text=rec["Question"], options=options, correct_index=ci, explanation=rec["Explanation"] or None, difficulty=difficulty, marks=marks)
    except ValidationError as e:
        msgs = []
        for err in e.errors():
            field = FIELD_NAMES.get(str(err["loc"][-1]) if err["loc"] else "", "Row")
            msgs.append(f"{field}: {err['msg'].removeprefix('Value error, ')}")
        raise ValueError("; ".join(msgs)) from None


def import_questions(db: Session, user: User, bank: QuestionBank, data: bytes, filename: str, *, dry_run: bool, request: Request) -> ImportResult:
    rows = _read_rows(data)
    existing = {_norm(t) for t in db.scalars(select(BankQuestion.text).where(BankQuestion.bank_id == bank.id)).all()}
    issues: list[ImportRowIssue] = []
    good: list[BankQuestionIn] = []
    duplicates = 0
    for n, rec in rows:
        try:
            q = _parse(rec)
        except ValueError as e:
            issues.append(ImportRowIssue(row=n, message=str(e)))
            continue
        key = _norm(q.text)
        if key in existing:
            duplicates += 1
            issues.append(ImportRowIssue(row=n, message="Already in this bank (or repeated in the file); skipped", skipped=True))
            continue
        existing.add(key)
        good.append(q)
    if not dry_run and good:
        for q in good:
            db.add(BankQuestion(bank_id=bank.id, topic=q.topic, text=q.text.strip(), options=q.options, correct_index=q.correct_index, explanation=q.explanation,
                                difficulty=q.difficulty, marks=q.marks, source="import", verified_by=None, created_by=user.id))
        audit_service.log_action(db, "question_bank.imported", actor=user, entity_type="question_bank", entity_id=bank.id,
                                 details={"file": filename[:120], "imported": len(good), "rows": len(rows), "skipped": len(issues)}, request=request)
        db.commit()
    return ImportResult(dry_run=dry_run, total_rows=len(rows), valid=len(good), imported=0 if dry_run else len(good), duplicates=duplicates,
                        failed=sum(1 for i in issues if not i.skipped), issues=issues[:200])
