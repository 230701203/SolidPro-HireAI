from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, EmailLog, User
from tests.conftest import approved_employee, login, new_client, register, verify


def _register_employee(email="newbie@solidpro-test.com"):
    c = new_client()
    r = register(c, email, name="New Employee", mobile=None)
    assert r.status_code == 201
    return c


def test_company_email_registers_as_employee_pending_verification(admin):
    c = _register_employee()
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "newbie@solidpro-test.com"))
        assert u.role.value == "employee" and u.status.value == "pending_email_verification"
    r = login(c, "newbie@solidpro-test.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"


def test_verified_employee_waits_for_approval_and_admin_is_notified(admin):
    c = _register_employee()
    assert verify(c, "newbie@solidpro-test.com").json()["status"] == "pending_approval"

    r = login(c, "newbie@solidpro-test.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "pending_approval"

    pending = admin.get("/api/employees/pending").json()
    assert [e["email"] for e in pending] == ["newbie@solidpro-test.com"]

    notes = admin.get("/api/notifications").json()
    assert any(n["type"] == "employee_registration" for n in notes["items"])
    assert admin.get("/api/notifications/unread-count").json()["count"] >= 1
    with SessionLocal() as db:
        assert db.scalar(select(EmailLog).where(EmailLog.template == "employee_registration"))  # admin email queued


def test_approval_grants_exactly_the_chosen_permissions(admin):
    emp = approved_employee(admin, perms=("review_applications", "view_analytics"))
    me = emp.get("/api/auth/me").json()
    assert me["role"] == "employee" and me["status"] == "active"
    assert me["permissions"] == ["review_applications", "view_analytics"]

    # Employee got an in-app notification and an approval email.
    assert any(n["type"] == "employee_approved" for n in emp.get("/api/notifications").json()["items"])
    with SessionLocal() as db:
        assert db.scalar(select(EmailLog).where(EmailLog.template == "employee_approved"))
        assert db.scalar(select(AuditLog).where(AuditLog.action == "employee.approved"))

    detail = admin.get(f"/api/employees/{me['id']}").json()
    assert detail["approvals"][0]["decision"] == "approved"
    assert detail["approvals"][0]["decided_by_name"] == "Test Admin"


def test_reject_requires_reason_and_blocks_login(admin):
    c = _register_employee()
    verify(c, "newbie@solidpro-test.com")
    emp_id = admin.get("/api/employees/pending").json()[0]["id"]

    assert admin.post(f"/api/employees/{emp_id}/reject", json={"reason": ""}).status_code == 422
    assert admin.post(f"/api/employees/{emp_id}/reject", json={"reason": "Not a current employee"}).status_code == 200

    r = login(c, "newbie@solidpro-test.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_rejected"
    assert admin.get("/api/employees/pending").json() == []
    # Cannot reject twice.
    assert admin.post(f"/api/employees/{emp_id}/reject", json={"reason": "again"}).status_code == 409


def test_rejected_employee_can_be_approved_later(admin):
    c = _register_employee()
    verify(c, "newbie@solidpro-test.com")
    emp_id = admin.get("/api/employees/pending").json()[0]["id"]
    admin.post(f"/api/employees/{emp_id}/reject", json={"reason": "Wrong department"})
    r = admin.post(f"/api/employees/{emp_id}/approve", json={"permission_codes": ["manage_interviews"]})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert login(c, "newbie@solidpro-test.com").status_code == 200


def test_approve_rejects_unknown_permission_and_wrong_state(admin):
    c = _register_employee()
    verify(c, "newbie@solidpro-test.com")
    emp_id = admin.get("/api/employees/pending").json()[0]["id"]
    r = admin.post(f"/api/employees/{emp_id}/approve", json={"permission_codes": ["do_anything"]})
    assert r.status_code == 422
    assert admin.post(f"/api/employees/{emp_id}/approve", json={"permission_codes": []}).status_code == 200
    assert admin.post(f"/api/employees/{emp_id}/approve", json={"permission_codes": []}).status_code == 409  # already active


def test_admin_can_edit_permissions_of_active_employee(admin):
    emp = approved_employee(admin, perms=("review_applications",))
    emp_id = emp.get("/api/auth/me").json()["id"]
    r = admin.put(f"/api/employees/{emp_id}/permissions", json={"permission_codes": ["manage_job_openings", "schedule_tests"]})
    assert r.status_code == 200 and r.json() == ["manage_job_openings", "schedule_tests"]
    assert emp.get("/api/auth/me").json()["permissions"] == ["manage_job_openings", "schedule_tests"]
    with SessionLocal() as db:
        log = db.scalars(select(AuditLog).where(AuditLog.action == "employee.permissions_changed")).first()
        assert log.details["before"] == ["review_applications"]


def test_unverified_or_pending_employee_has_no_access_even_with_forged_context(admin):
    """A company email alone never grants employee privileges."""
    c = _register_employee()
    verify(c, "newbie@solidpro-test.com")
    assert c.get("/api/dashboard/summary").status_code == 401
    assert c.get("/api/employees").status_code == 401
    assert c.get("/api/notifications").status_code == 401


def test_external_email_never_enters_employee_queue(admin):
    register(new_client(), "outsider@gmail.com")
    assert admin.get("/api/employees/pending").json() == []


def test_deactivating_company_domain_turns_new_signups_into_applicants(admin):
    domains = admin.get("/api/settings/email-domains").json()
    dom = next(d for d in domains if d["domain"] == "solidpro-test.com")
    assert admin.patch(f"/api/settings/email-domains/{dom['id']}", json={"is_active": False}).status_code == 200
    register(new_client(), "late@solidpro-test.com")
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "late@solidpro-test.com")).role.value == "applicant"


def test_add_domain_validation_and_duplicates(admin):
    assert admin.post("/api/settings/email-domains", json={"domain": "@NewCo.com"}).json()["domain"] == "newco.com"
    assert admin.post("/api/settings/email-domains", json={"domain": "newco.com"}).status_code == 409
    assert admin.post("/api/settings/email-domains", json={"domain": "not a domain"}).status_code == 422
    c = new_client()
    register(c, "x@newco.com", mobile=None)
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "x@newco.com")).role.value == "employee"
