from collections import defaultdict
from datetime import date

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AccountStatus,
    ApplicationStatus,
    EmployeeAssignment,
    JobApplication,
    JobCategory,
    JobOpening,
    OpeningStatus,
    Role,
    User,
)
from app.models.base import utcnow
from app.schemas.recruitment import (
    CategoryIn,
    CategoryUpdate,
    OpeningCreate,
    OpeningUpdate,
)
from app.services import audit_service, notification_service

PENDING = (ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INFO_REQUESTED)
REQUIRED_ON_UPDATE = {"title", "category_id", "description", "employment_type", "work_mode", "vacancies"}


# ------------------------------------------------------------------ categories


def category_counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(JobOpening.category_id, func.count()).group_by(JobOpening.category_id)).all()
    return {cid: n for cid, n in rows}


def create_category(db: Session, data: CategoryIn, user: User, request: Request) -> JobCategory:
    if db.scalar(select(JobCategory.id).where(func.lower(JobCategory.name) == data.name.lower())):
        raise AppError(409, "category_exists", "A category with this name already exists.", fields={"name": "Already exists"})
    cat = JobCategory(name=data.name, description=data.description, is_internship=data.is_internship)
    db.add(cat)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "category_exists", "A category with this name already exists.") from exc
    audit_service.log_action(db, "category.created", actor=user, entity_type="job_category", entity_id=cat.id, details={"name": cat.name}, request=request)
    db.commit()
    return cat


def update_category(db: Session, cat: JobCategory, data: CategoryUpdate, user: User, request: Request) -> JobCategory:
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        name = " ".join(changes["name"].split())
        clash = db.scalar(select(JobCategory.id).where(func.lower(JobCategory.name) == name.lower(), JobCategory.id != cat.id))
        if clash:
            raise AppError(409, "category_exists", "A category with this name already exists.", fields={"name": "Already exists"})
        changes["name"] = name
    for k, v in changes.items():
        if v is None and k in ("name", "is_internship", "is_active"):
            continue
        setattr(cat, k, v)
    audit_service.log_action(db, "category.updated", actor=user, entity_type="job_category", entity_id=cat.id, details=changes, request=request)
    db.commit()
    return cat


# ------------------------------------------------------------------ helpers


def is_open(o: JobOpening) -> bool:
    return o.status == OpeningStatus.PUBLISHED and (o.deadline is None or o.deadline >= date.today())


def assignees_map(db: Session, opening_ids: list[int]) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = defaultdict(list)
    if not opening_ids:
        return result
    rows = db.execute(
        select(EmployeeAssignment.opening_id, User.id, User.full_name, User.email)
        .join(User, User.id == EmployeeAssignment.employee_id)
        .where(EmployeeAssignment.opening_id.in_(opening_ids))
        .order_by(User.full_name)
    ).all()
    for oid, uid, name, email in rows:
        result[oid].append({"id": uid, "full_name": name, "email": email})
    return result


def counts_map(db: Session, opening_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not opening_ids:
        return {}
    rows = db.execute(
        select(JobApplication.opening_id, JobApplication.status, func.count())
        .where(JobApplication.opening_id.in_(opening_ids))
        .group_by(JobApplication.opening_id, JobApplication.status)
    ).all()
    out: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for oid, status, n in rows:
        out[oid][0] += n
        if status in PENDING:
            out[oid][1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}


def get_opening(db: Session, opening_id: int) -> JobOpening:
    o = db.get(JobOpening, opening_id)
    if o is None:
        raise AppError(404, "not_found", "Opening not found.")
    return o


def _validate_assignees(db: Session, ids: list[int]) -> list[User]:
    ids = sorted(set(ids))
    if not ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    bad = [u for u in users if u.role != Role.EMPLOYEE or u.status != AccountStatus.ACTIVE]
    if len(users) != len(ids) or bad:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"assigned_employee_ids": "Only active employees can be assigned"})
    return list(users)


def _set_assignees(db: Session, opening: JobOpening, ids: list[int], actor: User) -> None:
    users = _validate_assignees(db, ids)
    current = set(db.scalars(select(EmployeeAssignment.employee_id).where(EmployeeAssignment.opening_id == opening.id)).all())
    wanted = {u.id for u in users}
    for uid in current - wanted:
        a = db.get(EmployeeAssignment, (opening.id, uid))
        if a:
            db.delete(a)
    for uid in wanted - current:
        db.add(EmployeeAssignment(opening_id=opening.id, employee_id=uid, assigned_by=actor.id))
        if uid != actor.id:
            notification_service.notify(
                db, uid, "opening_assigned", "Assigned to a job opening", f"You were assigned to “{opening.title}”.", f"/openings/{opening.id}"
            )
    db.flush()


def _check_category(db: Session, category_id: int, *, must_be_active: bool = True) -> JobCategory:
    cat = db.get(JobCategory, category_id)
    if cat is None or (must_be_active and not cat.is_active):
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"category_id": "Choose an active category"})
    return cat


# ------------------------------------------------------------------ openings


def create_opening(db: Session, data: OpeningCreate, user: User, request: Request) -> JobOpening:
    _check_category(db, data.category_id)
    payload = data.model_dump(exclude={"assigned_employee_ids"})
    opening = JobOpening(**payload, status=OpeningStatus.DRAFT, created_by=user.id)
    db.add(opening)
    db.flush()
    ids = list(data.assigned_employee_ids)
    if user.role == Role.EMPLOYEE and user.id not in ids:
        ids.append(user.id)  # creators always keep access to what they create
    _set_assignees(db, opening, ids, user)
    audit_service.log_action(db, "opening.created", actor=user, entity_type="job_opening", entity_id=opening.id, details={"title": opening.title}, request=request)
    db.commit()
    return opening


def update_opening(db: Session, opening: JobOpening, data: OpeningUpdate, user: User, request: Request) -> JobOpening:
    changes = data.model_dump(exclude_unset=True)
    ids = changes.pop("assigned_employee_ids", None)
    for k in REQUIRED_ON_UPDATE & changes.keys():
        if changes[k] is None:
            raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={k: "This field is required"})
    if "category_id" in changes and changes["category_id"] != opening.category_id:
        _check_category(db, changes["category_id"])
    for k, v in changes.items():
        setattr(opening, k, v)
    if ids is not None:
        if user.role == Role.EMPLOYEE and user.id not in ids:
            ids = [*ids, user.id]  # an employee cannot remove their own access by editing
        _set_assignees(db, opening, ids, user)
    audit_service.log_action(
        db, "opening.updated", actor=user, entity_type="job_opening", entity_id=opening.id,
        details={"fields": sorted(changes.keys()) + (["assignees"] if ids is not None else [])}, request=request,
    )
    db.commit()
    return opening


def publish(db: Session, opening: JobOpening, user: User, request: Request) -> JobOpening:
    if opening.status == OpeningStatus.PUBLISHED:
        raise AppError(409, "invalid_state", "This opening is already published.")
    cat = db.get(JobCategory, opening.category_id)
    problems: dict[str, str] = {}
    if not cat or not cat.is_active:
        problems["category_id"] = "The category is inactive"
    if not opening.required_skills:
        problems["required_skills"] = "Add at least one required skill before publishing"
    if opening.deadline and opening.deadline < date.today():
        problems["deadline"] = "The deadline is in the past"
    if problems:
        raise AppError(422, "cannot_publish", "This opening is not ready to publish.", fields=problems)
    opening.status = OpeningStatus.PUBLISHED
    opening.published_at = opening.published_at or utcnow()
    opening.closed_at = None
    audit_service.log_action(db, "opening.published", actor=user, entity_type="job_opening", entity_id=opening.id, request=request)
    db.commit()
    return opening


def unpublish(db: Session, opening: JobOpening, user: User, request: Request) -> JobOpening:
    if opening.status != OpeningStatus.PUBLISHED:
        raise AppError(409, "invalid_state", "Only published openings can be unpublished.")
    opening.status = OpeningStatus.DRAFT
    audit_service.log_action(db, "opening.unpublished", actor=user, entity_type="job_opening", entity_id=opening.id, request=request)
    db.commit()
    return opening


def close(db: Session, opening: JobOpening, user: User, request: Request) -> JobOpening:
    if opening.status == OpeningStatus.CLOSED:
        raise AppError(409, "invalid_state", "This opening is already closed.")
    opening.status = OpeningStatus.CLOSED
    opening.closed_at = utcnow()
    audit_service.log_action(db, "opening.closed", actor=user, entity_type="job_opening", entity_id=opening.id, request=request)
    db.commit()
    return opening


def delete_opening(db: Session, opening: JobOpening, user: User, request: Request) -> None:
    n = db.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.opening_id == opening.id)) or 0
    if n:
        raise AppError(409, "has_applications", f"This opening has {n} application(s) and cannot be deleted. Close it instead.")
    audit_service.log_action(db, "opening.deleted", actor=user, entity_type="job_opening", entity_id=opening.id, details={"title": opening.title}, request=request)
    db.delete(opening)
    db.commit()


def duplicate(db: Session, opening: JobOpening, user: User, request: Request) -> JobOpening:
    cols = [
        "category_id", "description", "responsibilities", "required_skills", "preferred_skills", "required_qualifications",
        "preferred_qualifications", "required_experience", "employment_type", "work_mode", "location", "vacancies",
        "intern_college", "intern_degree", "intern_department", "intern_graduation_year", "intern_duration",
        "intern_availability", "intern_stipend",
    ]
    copy = JobOpening(
        title=f"{opening.title} (Copy)"[:200],
        status=OpeningStatus.DRAFT,
        created_by=user.id,
        deadline=None,  # the old deadline would be stale
        **{c: getattr(opening, c) for c in cols},
    )
    db.add(copy)
    db.flush()
    if user.role == Role.EMPLOYEE:
        _set_assignees(db, copy, [user.id], user)
    audit_service.log_action(db, "opening.duplicated", actor=user, entity_type="job_opening", entity_id=copy.id, details={"source": opening.id}, request=request)
    db.commit()
    return copy
