"""Reusable aptitude question bank. Questions here are copied into assessments, never referenced live."""

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.mock_content import APTITUDE_SEED
from app.core.errors import AppError
from app.models import BankQuestion, Difficulty, JobCategory, QuestionBank, User
from app.schemas.assessment import BankCreate, BankOut, BankQuestionIn, BankQuestionOut, BankQuestionUpdate, BankUpdate
from app.services import audit_service

SEED_BANK_NAME = "General aptitude (starter set)"


def sync_seed_bank(db: Session) -> int:
    """Create the starter bank once. It is a convenience: SolidPro should review and extend it."""
    if db.scalar(select(QuestionBank.id).where(QuestionBank.name == SEED_BANK_NAME)):
        return 0
    bank = QuestionBank(name=SEED_BANK_NAME, description="Starter aptitude questions for all roles. Review and extend before relying on them.", is_active=True)
    db.add(bank)
    db.flush()
    for topic, text, options, ci, expl, diff in APTITUDE_SEED:
        db.add(BankQuestion(bank_id=bank.id, topic=topic, text=text, options=options, correct_index=ci, explanation=expl, difficulty=Difficulty(diff), marks=1, source="seed"))
    db.flush()
    return len(APTITUDE_SEED)


def _bank_out(db: Session, b: QuestionBank) -> BankOut:
    total = db.scalar(select(func.count()).select_from(BankQuestion).where(BankQuestion.bank_id == b.id)) or 0
    active = db.scalar(select(func.count()).select_from(BankQuestion).where(BankQuestion.bank_id == b.id, BankQuestion.is_active.is_(True))) or 0
    cat = db.get(JobCategory, b.category_id) if b.category_id else None
    return BankOut(id=b.id, name=b.name, description=b.description, category_id=b.category_id, category_name=cat.name if cat else None,
                   is_active=b.is_active, question_count=total, active_question_count=active)


def list_banks(db: Session) -> list[BankOut]:
    return [_bank_out(db, b) for b in db.scalars(select(QuestionBank).order_by(QuestionBank.name)).all()]


def _get_bank(db: Session, bank_id: int) -> QuestionBank:
    b = db.get(QuestionBank, bank_id)
    if b is None:
        raise AppError(404, "not_found", "Question bank not found.")
    return b


def _check_category(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(JobCategory, category_id) is None:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"category_id": "Choose an existing category"})


def _name_free(db: Session, name: str, except_id: int | None = None) -> None:
    q = select(QuestionBank.id).where(func.lower(QuestionBank.name) == name.strip().lower())
    if except_id:
        q = q.where(QuestionBank.id != except_id)
    if db.scalar(q):
        raise AppError(409, "duplicate", "A question bank with this name already exists.", fields={"name": "Already exists"})


def create_bank(db: Session, user: User, data: BankCreate, request: Request) -> BankOut:
    _name_free(db, data.name)
    _check_category(db, data.category_id)
    b = QuestionBank(name=data.name.strip(), description=data.description, category_id=data.category_id, created_by=user.id)
    db.add(b)
    db.flush()
    audit_service.log_action(db, "question_bank.created", actor=user, entity_type="question_bank", entity_id=b.id, request=request)
    db.commit()
    return _bank_out(db, b)


def update_bank(db: Session, user: User, bank_id: int, data: BankUpdate, request: Request) -> BankOut:
    b = _get_bank(db, bank_id)
    patch = data.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"]:
        _name_free(db, patch["name"], b.id)
        b.name = patch["name"].strip()
    if "category_id" in patch:
        _check_category(db, patch["category_id"])
        b.category_id = patch["category_id"]
    for f in ("description", "is_active"):
        if f in patch and patch[f] is not None or f == "description" and f in patch:
            setattr(b, f, patch[f])
    audit_service.log_action(db, "question_bank.updated", actor=user, entity_type="question_bank", entity_id=b.id, details={"fields": sorted(patch)}, request=request)
    db.commit()
    return _bank_out(db, b)


def _q_out(db: Session, q: BankQuestion) -> BankQuestionOut:
    v = db.get(User, q.verified_by) if q.verified_by else None
    return BankQuestionOut(id=q.id, bank_id=q.bank_id, topic=q.topic, text=q.text, options=list(q.options), correct_index=q.correct_index,
                           explanation=q.explanation, difficulty=q.difficulty, marks=q.marks, is_active=q.is_active, source=q.source,
                           verified_by_name=v.full_name if v else None, updated_at=q.updated_at)


def list_questions(db: Session, bank_id: int, *, topic=None, difficulty=None, active=None, search=None, page=1, page_size=20):
    _get_bank(db, bank_id)
    q = select(BankQuestion).where(BankQuestion.bank_id == bank_id)
    if topic:
        q = q.where(BankQuestion.topic == topic)
    if difficulty:
        q = q.where(BankQuestion.difficulty == Difficulty(difficulty))
    if active is not None:
        q = q.where(BankQuestion.is_active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(BankQuestion.text.ilike(like), BankQuestion.topic.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(BankQuestion.id).limit(page_size).offset((page - 1) * page_size)).all()
    return [_q_out(db, r) for r in rows], total


def create_question(db: Session, user: User, bank_id: int, data: BankQuestionIn, request: Request) -> BankQuestionOut:
    _get_bank(db, bank_id)
    q = BankQuestion(bank_id=bank_id, topic=data.topic, text=data.text.strip(), options=data.options, correct_index=data.correct_index,
                     explanation=data.explanation, difficulty=data.difficulty, marks=data.marks, source="manual", verified_by=user.id, created_by=user.id)
    db.add(q)
    db.flush()
    audit_service.log_action(db, "question_bank.question_created", actor=user, entity_type="bank_question", entity_id=q.id, request=request)
    db.commit()
    return _q_out(db, q)


def update_question(db: Session, user: User, bank_id: int, question_id: int, data: BankQuestionUpdate, request: Request) -> BankQuestionOut:
    q = db.get(BankQuestion, question_id)
    if q is None or q.bank_id != bank_id:
        raise AppError(404, "not_found", "Question not found.")
    patch = data.model_dump(exclude_unset=True)
    options = patch.get("options", q.options)
    ci = patch.get("correct_index", q.correct_index)
    if not 0 <= ci < len(options):
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"correct_index": "Mark one of the options as correct"})
    for k, v in patch.items():
        if v is not None:
            setattr(q, k, v.strip() if k == "text" else v)
    if {"text", "options", "correct_index", "explanation"} & patch.keys():
        q.verified_by = user.id  # a person re-checked the key
    audit_service.log_action(db, "question_bank.question_updated", actor=user, entity_type="bank_question", entity_id=q.id, details={"fields": sorted(patch)}, request=request)
    db.commit()
    return _q_out(db, q)
