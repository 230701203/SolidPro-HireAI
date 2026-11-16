from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUser, DbSession, ManageCategories
from app.core.errors import AppError
from app.models import JobCategory, Role
from app.schemas.recruitment import CategoryIn, CategoryOut, CategoryUpdate
from app.services import opening_service

router = APIRouter(prefix="/job-categories", tags=["Job categories"])


def _out(cat: JobCategory, counts: dict[int, int]) -> CategoryOut:
    out = CategoryOut.model_validate(cat)
    out.openings_count = counts.get(cat.id, 0)
    return out


@router.get("", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DbSession, include_inactive: bool = False):
    q = select(JobCategory).order_by(JobCategory.name)
    staff = user.role in (Role.ADMIN, Role.EMPLOYEE)
    if not (staff and include_inactive):
        q = q.where(JobCategory.is_active.is_(True))
    counts = opening_service.category_counts(db) if staff else {}
    return [_out(c, counts) for c in db.scalars(q).all()]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, request: Request, user: ManageCategories, db: DbSession):
    return _out(opening_service.create_category(db, data, user, request), {})


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryUpdate, request: Request, user: ManageCategories, db: DbSession):
    cat = db.get(JobCategory, category_id)
    if cat is None:
        raise AppError(404, "not_found", "Category not found.")
    cat = opening_service.update_category(db, cat, data, user, request)
    return _out(cat, opening_service.category_counts(db))
