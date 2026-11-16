from datetime import date, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog
from tests.conftest import (
    applicant_client,
    approved_employee,
    category_id,
    make_opening,
    opening_payload,
    recruiter,
    user_id,
)

# ------------------------------------------------------------------ categories


def test_default_categories_seeded(admin):
    cats = {c["name"]: c for c in admin.get("/api/job-categories").json()}
    assert {"CAD", "Digital Transform", "Intern"} <= set(cats)
    assert cats["Intern"]["is_internship"] is True and cats["CAD"]["is_internship"] is False


def test_category_management_permissions_and_duplicates(admin):
    mgr = approved_employee(admin, "mgr@solidpro-test.com", ("manage_categories",))
    plain = approved_employee(admin, "plain@solidpro-test.com", ("review_applications",))
    applicant = applicant_client("cat@gmail.com", complete=False, resume=False)

    assert admin.post("/api/job-categories", json={"name": "Python Developer"}).status_code == 201
    r = mgr.post("/api/job-categories", json={"name": "  AI/ML   Engineer "})
    assert r.status_code == 201 and r.json()["name"] == "AI/ML Engineer"
    assert admin.post("/api/job-categories", json={"name": "python developer"}).status_code == 409  # case-insensitive
    assert plain.post("/api/job-categories", json={"name": "Nope"}).status_code == 403
    assert applicant.post("/api/job-categories", json={"name": "Nope"}).status_code == 403
    assert admin.post("/api/job-categories", json={"name": "x"}).status_code == 422

    cid = category_id(admin, "Python Developer")
    assert admin.patch(f"/api/job-categories/{cid}", json={"name": "CAD"}).status_code == 409
    assert admin.patch(f"/api/job-categories/{cid}", json={"is_active": False}).json()["is_active"] is False
    assert "Python Developer" not in [c["name"] for c in applicant.get("/api/job-categories").json()]  # applicants see active only
    assert "Python Developer" in [c["name"] for c in admin.get("/api/job-categories", params={"include_inactive": True}).json()]
    r = admin.post("/api/job-openings", json=opening_payload(cid))
    assert r.status_code == 422 and "category_id" in r.json()["error"]["fields"]  # cannot use an inactive category


# ------------------------------------------------------------------ openings: CRUD, scoping


def test_opening_creation_requires_permission_and_creator_is_assigned(admin):
    rec = recruiter(admin)
    viewer = approved_employee(admin, "viewer@solidpro-test.com", ("review_applications",))
    r = viewer.post("/api/job-openings", json=opening_payload(category_id(admin, "CAD")))
    assert r.status_code == 403
    o = make_opening(rec, publish=False)
    assert o["status"] == "draft" and [a["id"] for a in o["assignees"]] == [user_id(rec)]
    assert o["created_by_name"] == "Emp Loyee"


def test_employees_only_see_their_assigned_openings(admin):
    a = recruiter(admin, "a@solidpro-test.com")
    b = recruiter(admin, "b@solidpro-test.com")
    oa = make_opening(a, publish=False, title="Opening A")
    ob = make_opening(b, publish=False, title="Opening B")
    assert [i["title"] for i in a.get("/api/job-openings").json()["items"]] == ["Opening A"]
    assert a.get(f"/api/job-openings/{oa['id']}").status_code == 200
    assert a.get(f"/api/job-openings/{ob['id']}").status_code == 404  # looks nonexistent, not forbidden
    assert a.patch(f"/api/job-openings/{ob['id']}", json={"title": "Hijacked"}).status_code == 404
    assert a.delete(f"/api/job-openings/{ob['id']}").status_code == 404
    assert a.post(f"/api/job-openings/{ob['id']}/publish").status_code == 404
    assert admin.get("/api/job-openings").json()["total"] == 2  # admin sees everything


def test_applicants_cannot_use_staff_opening_endpoints(admin):
    o = make_opening(admin)
    ap = applicant_client("x@gmail.com", complete=False, resume=False)
    assert ap.get("/api/job-openings").status_code == 403
    assert ap.get(f"/api/job-openings/{o['id']}").status_code == 403
    assert ap.post("/api/job-openings", json=opening_payload(1)).status_code == 403


def test_opening_update_validation_and_filters(admin):
    o = make_opening(admin, publish=False, title="Embedded Dev", required_skills=["C", "c", " RTOS ", ""])
    assert o["required_skills"] == ["C", "RTOS"]  # trimmed + de-duplicated
    r = admin.patch(f"/api/job-openings/{o['id']}", json={"title": None})
    assert r.status_code == 422
    r = admin.patch(f"/api/job-openings/{o['id']}", json={"vacancies": 0})
    assert r.status_code == 422
    r = admin.patch(f"/api/job-openings/{o['id']}", json={"location": "Chennai", "vacancies": 5})
    assert r.json()["location"] == "Chennai" and r.json()["vacancies"] == 5 and r.json()["title"] == "Embedded Dev"

    make_opening(admin, cat="Digital Transform", title="Data Lead")
    assert admin.get("/api/job-openings", params={"status": "draft"}).json()["total"] == 1
    assert admin.get("/api/job-openings", params={"category_id": category_id(admin, "Digital Transform")}).json()["total"] == 1
    assert admin.get("/api/job-openings", params={"search": "embedded"}).json()["total"] == 1
    assert admin.get("/api/job-openings", params={"page_size": 1}).json()["pages"] == 2


def test_internship_fields_are_stored(admin):
    o = make_opening(
        admin, cat="Intern", employment_type="internship", title="Digital Transformation Intern",
        intern_college="REC", intern_degree="B.E.", intern_department="CSE", intern_graduation_year=2027,
        intern_duration="6 months", intern_availability="Immediate", intern_stipend="₹15,000/month",
    )
    assert o["category_is_internship"] is True and o["intern_duration"] == "6 months" and o["intern_graduation_year"] == 2027
    ap = applicant_client("intern@gmail.com", complete=False, resume=False)
    job = ap.get(f"/api/jobs/{o['id']}").json()
    assert job["is_internship"] is True and job["intern_stipend"] == "₹15,000/month"


# ------------------------------------------------------------------ publish lifecycle and applicant visibility


def test_publish_validation(admin):
    o = make_opening(admin, publish=False, required_skills=[])
    r = admin.post(f"/api/job-openings/{o['id']}/publish")
    assert r.status_code == 422 and "required_skills" in r.json()["error"]["fields"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    admin.patch(f"/api/job-openings/{o['id']}", json={"required_skills": ["Python"], "deadline": yesterday})
    r = admin.post(f"/api/job-openings/{o['id']}/publish")
    assert r.status_code == 422 and "deadline" in r.json()["error"]["fields"]
    admin.patch(f"/api/job-openings/{o['id']}", json={"deadline": (date.today() + timedelta(days=7)).isoformat()})
    assert admin.post(f"/api/job-openings/{o['id']}/publish").json()["status"] == "published"
    assert admin.post(f"/api/job-openings/{o['id']}/publish").status_code == 409


def test_only_published_open_openings_are_visible_to_applicants(admin):
    ap = applicant_client("viewer@gmail.com", complete=False, resume=False)
    draft = make_opening(admin, publish=False, title="Hidden Draft")
    live = make_opening(admin, title="Live Job")
    def titles():
        return [j["title"] for j in ap.get("/api/jobs").json()["items"]]

    assert titles() == ["Live Job"]
    assert ap.get(f"/api/jobs/{draft['id']}").status_code == 404

    admin.post(f"/api/job-openings/{live['id']}/unpublish")
    assert titles() == []
    admin.post(f"/api/job-openings/{live['id']}/publish")
    assert titles() == ["Live Job"]
    admin.post(f"/api/job-openings/{live['id']}/close")
    assert titles() == []
    assert admin.post(f"/api/job-openings/{live['id']}/close").status_code == 409
    assert admin.post(f"/api/job-openings/{live['id']}/publish").status_code == 200  # can be reopened
    assert titles() == ["Live Job"]

    # Applicant payload never leaks internal data.
    job = ap.get(f"/api/jobs/{live['id']}").json()
    assert "assignees" not in job and "created_by_name" not in job and "applications_count" not in job

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    admin.patch(f"/api/job-openings/{live['id']}", json={"deadline": yesterday})
    assert titles() == []  # past deadline hides it even though status is still published


def test_job_board_search_and_filter(admin):
    make_opening(admin, title="CAD Designer", cat="CAD")
    make_opening(admin, title="Data Engineer", cat="Digital Transform")
    ap = applicant_client("s@gmail.com", complete=False, resume=False)
    assert ap.get("/api/jobs", params={"search": "designer"}).json()["total"] == 1
    assert ap.get("/api/jobs", params={"category_id": category_id(ap, "Digital Transform")}).json()["total"] == 1
    assert ap.get("/api/jobs").json()["total"] == 2


def test_delete_and_duplicate(admin):
    o = make_opening(admin, publish=False)
    assert admin.delete(f"/api/job-openings/{o['id']}").status_code == 204
    assert admin.get(f"/api/job-openings/{o['id']}").status_code == 404

    src = make_opening(admin, deadline=(date.today() + timedelta(days=30)).isoformat(), title="Original")
    dup = admin.post(f"/api/job-openings/{src['id']}/duplicate")
    assert dup.status_code == 201
    d = dup.json()
    assert d["id"] != src["id"] and d["title"] == "Original (Copy)" and d["status"] == "draft"
    assert d["deadline"] is None and d["required_skills"] == src["required_skills"]

    ap = applicant_client("del@gmail.com")
    assert ap.post("/api/applications", json={"opening_id": src["id"]}).status_code == 201
    r = admin.delete(f"/api/job-openings/{src['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "has_applications"


def test_assignment_rules_and_notification(admin):
    rec = recruiter(admin, "owner@solidpro-test.com")
    other = recruiter(admin, "other@solidpro-test.com")
    o = make_opening(rec, publish=False)
    oid = o["id"]
    assert other.get(f"/api/job-openings/{oid}").status_code == 404

    assignable = rec.get("/api/job-openings/assignable-employees").json()
    assert {u["email"] for u in assignable} >= {"owner@solidpro-test.com", "other@solidpro-test.com"}

    r = rec.patch(f"/api/job-openings/{oid}", json={"assigned_employee_ids": [user_id(other)]})
    assert r.status_code == 200
    assert {a["id"] for a in r.json()["assignees"]} == {user_id(rec), user_id(other)}  # creator cannot lock themselves out
    assert other.get(f"/api/job-openings/{oid}").status_code == 200
    assert any(n["type"] == "opening_assigned" for n in other.get("/api/notifications").json()["items"])

    applicant_id = user_id(applicant_client("notemp@gmail.com", complete=False, resume=False))
    r = admin.patch(f"/api/job-openings/{oid}", json={"assigned_employee_ids": [applicant_id]})
    assert r.status_code == 422 and "assigned_employee_ids" in r.json()["error"]["fields"]

    r = admin.patch(f"/api/job-openings/{oid}", json={"assigned_employee_ids": [user_id(other)]})
    assert [a["id"] for a in r.json()["assignees"]] == [user_id(other)]  # admin may override fully
    assert rec.get(f"/api/job-openings/{oid}").status_code == 404


def test_audit_trail_for_recruitment_changes(admin):
    o = make_opening(admin)
    admin.post(f"/api/job-openings/{o['id']}/close")
    with SessionLocal() as db:
        actions = {a.action for a in db.scalars(select(AuditLog)).all()}
    assert {"opening.created", "opening.published", "opening.closed"} <= actions
