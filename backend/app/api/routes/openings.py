from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, or_, select

from app.api.dependencies.auth import (
    DbSession,
    ManageOpenings,
    ReviewApplications,
    StaffUser,
)
from app.models import AccountStatus, JobCategory, JobOpening, OpeningStatus, Role, User
from app.schemas.common import make_page
from app.schemas.recruitment import (
    ApplicationListItem,
    AssigneeOut,
    OpeningCreate,
    OpeningListItem,
    OpeningOut,
    OpeningUpdate,
)
from app.services import access, application_service, opening_service
from app.services.opening_service import assignees_map, counts_map, is_open

router = APIRouter(prefix="/job-openings", tags=["Job openings"])


def _full(db, o: JobOpening) -> OpeningOut:
    counts = counts_map(db, [o.id]).get(o.id, (0, 0))
    creator = db.get(User, o.created_by) if o.created_by else None
    base = {c.name: getattr(o, c.name) for c in JobOpening.__table__.columns if c.name in OpeningCreate.model_fields}
    return OpeningOut(
        **base, id=o.id, status=o.status, category_name=o.category.name, category_is_internship=o.category.is_internship, is_open=is_open(o),
        published_at=o.published_at, closed_at=o.closed_at, created_at=o.created_at, created_by_name=creator.full_name if creator else None,
        applications_count=counts[0], assignees=assignees_map(db, [o.id]).get(o.id, []),
    )


def _scoped(db, user: User, opening_id: int) -> JobOpening:
    access.require_opening_access(db, user, opening_id)
    return opening_service.get_opening(db, opening_id)


def _managed(db, user: User, opening_id: int) -> JobOpening:
    """Edit actions need the permission (route dependency) AND assignment (employees)."""
    return _scoped(db, user, opening_id)


@router.get("/assignable-employees", response_model=list[AssigneeOut])
def assignable_employees(_: ManageOpenings, db: DbSession):
    rows = db.scalars(select(User).where(User.role == Role.EMPLOYEE, User.status == AccountStatus.ACTIVE).order_by(User.full_name)).all()
    return [AssigneeOut(id=u.id, full_name=u.full_name, email=u.email) for u in rows]


@router.get("")
def list_openings(
    user: StaffUser, db: DbSession,
    category_id: int | None = None, status: OpeningStatus | None = None,
    search: str | None = Query(default=None, max_length=100), assigned_to_me: bool = False,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    q = select(JobOpening)
    scope = access.staff_scope(db, user)
    if scope is not None:
        q = q.where(JobOpening.id.in_(scope))
    elif assigned_to_me:
        from app.models import EmployeeAssignment

        q = q.where(JobOpening.id.in_(select(EmployeeAssignment.opening_id).where(EmployeeAssignment.employee_id == user.id)))
    if category_id:
        q = q.where(JobOpening.category_id == category_id)
    if status:
        q = q.where(JobOpening.status == status)
    if search:
        like = f"%{search.strip()}%"
        q = q.join(JobCategory, JobCategory.id == JobOpening.category_id).where(or_(JobOpening.title.ilike(like), JobCategory.name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(JobOpening.created_at.desc(), JobOpening.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    ids = [o.id for o in rows]
    counts, people = counts_map(db, ids), assignees_map(db, ids)
    items = [
        OpeningListItem(
            id=o.id, title=o.title, category_id=o.category_id, category_name=o.category.name, status=o.status, employment_type=o.employment_type,
            work_mode=o.work_mode, location=o.location, vacancies=o.vacancies, deadline=o.deadline, is_open=is_open(o),
            applications_count=counts.get(o.id, (0, 0))[0], pending_count=counts.get(o.id, (0, 0))[1], assignees=people.get(o.id, []), created_at=o.created_at,
        )
        for o in rows
    ]
    return make_page(items, total, page, page_size)


@router.post("", response_model=OpeningOut, status_code=201)
def create_opening(data: OpeningCreate, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.create_opening(db, data, user, request))


@router.get("/{opening_id}", response_model=OpeningOut)
def get_opening(opening_id: int, user: StaffUser, db: DbSession):
    return _full(db, _scoped(db, user, opening_id))


@router.patch("/{opening_id}", response_model=OpeningOut)
def update_opening(opening_id: int, data: OpeningUpdate, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.update_opening(db, _managed(db, user, opening_id), data, user, request))


@router.post("/{opening_id}/publish", response_model=OpeningOut)
def publish(opening_id: int, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.publish(db, _managed(db, user, opening_id), user, request))


@router.post("/{opening_id}/unpublish", response_model=OpeningOut)
def unpublish(opening_id: int, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.unpublish(db, _managed(db, user, opening_id), user, request))


@router.post("/{opening_id}/close", response_model=OpeningOut)
def close(opening_id: int, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.close(db, _managed(db, user, opening_id), user, request))


@router.post("/{opening_id}/duplicate", response_model=OpeningOut, status_code=201)
def duplicate(opening_id: int, request: Request, user: ManageOpenings, db: DbSession):
    return _full(db, opening_service.duplicate(db, _managed(db, user, opening_id), user, request))


@router.delete("/{opening_id}", status_code=204)
def delete_opening(opening_id: int, request: Request, user: ManageOpenings, db: DbSession):
    opening_service.delete_opening(db, _managed(db, user, opening_id), user, request)
    return Response(status_code=204)


@router.get("/{opening_id}/applications")
def opening_applications(
    opening_id: int, user: ReviewApplications, db: DbSession, status=None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
):
    from app.models import ApplicationStatus

    _scoped(db, user, opening_id)
    st = ApplicationStatus(status) if status else None
    items, total = application_service.list_applications(db, opening_id=opening_id, status=st, page=page, page_size=page_size)
    return make_page([ApplicationListItem(**i) for i in items], total, page, page_size)
