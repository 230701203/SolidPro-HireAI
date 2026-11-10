import pytest
from sqlalchemy import select

from app.api.dependencies.auth import require_permission
from app.database import SessionLocal
from app.models import AuditLog, EmailLog, Role
from tests.conftest import (
    approved_employee,
    latest_token,
    login,
    make_active_user,
    new_client,
    register,
    verify,
)

ADMIN_ONLY_GET = ["/api/users", "/api/employees", "/api/employees/pending", "/api/permissions", "/api/audit-logs", "/api/settings/email-domains", "/api/settings/email-logs"]


def _applicant_client(email="app@gmail.com"):
    c = new_client()
    register(c, email)
    verify(c, email)
    assert login(c, email).status_code == 200
    return c


@pytest.mark.parametrize("path", ADMIN_ONLY_GET)
def test_admin_endpoints_forbidden_for_applicants_and_employees(admin, path):
    applicant = _applicant_client()
    employee = approved_employee(admin, perms=("manage_job_openings",))
    assert applicant.get(path).status_code == 403
    assert employee.get(path).status_code == 403  # approval + permissions never imply admin access
    assert admin.get(path).status_code == 200


def test_employee_cannot_approve_or_change_permissions(admin):
    employee = approved_employee(admin)
    me = employee.get("/api/auth/me").json()
    assert employee.post(f"/api/employees/{me['id']}/approve", json={"permission_codes": ["view_analytics"]}).status_code == 403
    assert employee.put(f"/api/employees/{me['id']}/permissions", json={"permission_codes": ["view_analytics"]}).status_code == 403
    assert employee.get("/api/auth/me").json()["permissions"] == ["review_applications"]  # no privilege escalation


def test_require_permission_dependency_logic(admin):
    """Admin passes everything; employees only what was granted; applicants nothing."""
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient


    probe = FastAPI()
    from app.core.errors import register_error_handlers

    register_error_handlers(probe)

    @probe.get("/needs-review", dependencies=[Depends(require_permission("review_applications"))])
    def a():
        return {"ok": True}

    @probe.get("/needs-analytics", dependencies=[Depends(require_permission("view_analytics"))])
    def b():
        return {"ok": True}

    employee = approved_employee(admin, perms=("review_applications",))
    token_cookie = employee.cookies.get("hireai_session")
    admin_cookie = admin.cookies.get("hireai_session")
    applicant_cookie = _applicant_client("probe@gmail.com").cookies.get("hireai_session")

    def call(path, cookie):
        c = TestClient(probe)
        c.cookies.set("hireai_session", cookie)
        return c.get(path).status_code

    assert call("/needs-review", token_cookie) == 200
    assert call("/needs-analytics", token_cookie) == 403
    assert call("/needs-review", admin_cookie) == 200 and call("/needs-analytics", admin_cookie) == 200
    assert call("/needs-review", applicant_cookie) == 403


# ------------------------------------------------------------------ user management


def test_user_list_search_filter_pagination(admin):
    for i in range(5):
        make_active_user(f"person{i}@gmail.com", Role.APPLICANT, name=f"Person {i}")
    r = admin.get("/api/users", params={"role": "applicant", "page_size": 2}).json()
    assert r["total"] == 5 and len(r["items"]) == 2 and r["pages"] == 3
    r = admin.get("/api/users", params={"search": "person3"}).json()
    assert [u["email"] for u in r["items"]] == ["person3@gmail.com"]
    r = admin.get("/api/users", params={"role": "admin"}).json()
    assert r["total"] == 1
    assert "password_hash" not in str(r)
    assert admin.get("/api/users", params={"page_size": 1000}).status_code == 422


def test_suspend_blocks_access_immediately_and_reactivate_restores(admin):
    applicant = _applicant_client()
    uid = applicant.get("/api/auth/me").json()["id"]

    r = admin.patch(f"/api/users/{uid}/status", json={"status": "suspended", "reason": "policy"})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert applicant.get("/api/auth/me").status_code in (401, 403)  # live session is dead
    r = login(new_client(), "app@gmail.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_suspended"

    assert admin.patch(f"/api/users/{uid}/status", json={"status": "active"}).status_code == 200
    assert login(new_client(), "app@gmail.com").status_code == 200
    with SessionLocal() as db:
        assert {a.action for a in db.scalars(select(AuditLog)).all()} >= {"user.suspended", "user.active"}


def test_suspended_employee_loses_access(admin):
    emp = approved_employee(admin)
    uid = emp.get("/api/auth/me").json()["id"]
    admin.patch(f"/api/users/{uid}/status", json={"status": "suspended"})
    assert emp.get("/api/dashboard/summary").status_code in (401, 403)


def test_admin_cannot_change_own_status_or_unfinished_registrations(admin):
    my_id = admin.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/users/{my_id}/status", json={"status": "suspended"}).status_code == 409
    c = new_client()
    register(c, "pending@solidpro-test.com", mobile=None)
    pending_id = next(u["id"] for u in admin.get("/api/users").json()["items"] if u["email"] == "pending@solidpro-test.com")
    assert admin.patch(f"/api/users/{pending_id}/status", json={"status": "active"}).status_code == 409  # must verify + be approved
    assert admin.patch(f"/api/users/{my_id}/status", json={"status": "bogus"}).status_code == 422
    assert admin.patch("/api/users/99999/status", json={"status": "active"}).status_code == 404


def test_admin_initiated_password_reset_emails_user(admin):
    applicant = _applicant_client()
    uid = applicant.get("/api/auth/me").json()["id"]
    assert admin.post(f"/api/users/{uid}/password-reset").status_code == 200
    token = latest_token("app@gmail.com", "password_reset")
    new_pw = "ResetByAdmin#2026"
    assert new_client().post("/api/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 200
    assert login(new_client(), "app@gmail.com", new_pw).status_code == 200


def test_unlock_user(admin):
    from app.core.config import get_settings

    _applicant_client("lockme@gmail.com")
    for _ in range(get_settings().max_failed_logins):
        login(new_client(), "lockme@gmail.com", "WrongPassw0rd!")
    assert login(new_client(), "lockme@gmail.com").status_code == 429
    uid = next(u["id"] for u in admin.get("/api/users").json()["items"] if u["email"] == "lockme@gmail.com")
    assert admin.post(f"/api/users/{uid}/unlock").status_code == 200
    assert login(new_client(), "lockme@gmail.com").status_code == 200


# ------------------------------------------------------------------ notifications, audit, dashboard, email logs


def test_notifications_are_private_and_markable(admin):
    a1 = _applicant_client("n1@gmail.com")
    a2 = _applicant_client("n2@gmail.com")
    n1 = a1.get("/api/notifications").json()["items"]
    assert n1 and all(n["type"] == "welcome" for n in n1)
    nid = n1[0]["id"]
    assert a2.post(f"/api/notifications/{nid}/read").status_code == 404  # not yours
    assert a1.get("/api/notifications/unread-count").json()["count"] == 1
    assert a1.post(f"/api/notifications/{nid}/read").json()["is_read"] is True
    assert a1.get("/api/notifications/unread-count").json()["count"] == 0
    assert a1.post("/api/notifications/read-all").status_code == 200
    assert a1.get("/api/notifications", params={"unread_only": True}).json()["total"] == 0


def test_audit_log_filters(admin):
    _applicant_client()
    r = admin.get("/api/audit-logs", params={"action": "auth.register"}).json()
    assert r["total"] == 1 and r["items"][0]["action"] == "auth.register"
    r = admin.get("/api/audit-logs", params={"search": "admin@solidpro-test.com"}).json()
    assert r["total"] >= 2 and all(i["actor_email"] == "admin@solidpro-test.com" for i in r["items"])
    assert admin.get("/api/audit-logs", params={"date_from": "2999-01-01"}).json()["total"] == 0


def test_dashboard_numbers_come_from_database(admin):
    _applicant_client("d1@gmail.com")
    _applicant_client("d2@gmail.com")
    approved_employee(admin, "active.emp@solidpro-test.com")
    c = new_client()
    register(c, "pend.emp@solidpro-test.com", mobile=None)
    verify(c, "pend.emp@solidpro-test.com")

    d = admin.get("/api/dashboard/summary").json()
    assert d["cards"] == {"total_applicants": 2, "total_employees": 1, "pending_employee_approvals": 1, "suspended_accounts": 0}
    assert len(d["registrations_by_day"]) == 30
    assert sum(x["applicants"] for x in d["registrations_by_day"]) == 2
    assert [u["email"] for u in d["recent_employee_requests"]] == ["pend.emp@solidpro-test.com"]


def test_dashboard_is_role_specific(admin):
    emp = approved_employee(admin)
    assert emp.get("/api/dashboard/summary").json()["permissions"] == ["review_applications"]
    ap = _applicant_client()
    body = ap.get("/api/dashboard/summary").json()
    assert body["role"] == "applicant" and "cards" not in body


def test_email_log_retry(admin):
    with SessionLocal() as db:
        from app.models import EmailStatus

        log = EmailLog(to_email="x@gmail.com", subject="s", template="t", body_text="b", body_html="<p>b</p>", status=EmailStatus.FAILED, error="smtp down")
        db.add(log)
        db.commit()
        lid = log.id
    r = admin.post(f"/api/settings/email-logs/{lid}/retry")
    assert r.status_code == 200
    again = admin.get("/api/settings/email-logs", params={"status": "dev_logged"}).json()
    assert any(i["id"] == lid for i in again["items"])  # retried; honestly marked as dev-logged
    assert admin.post(f"/api/settings/email-logs/{lid}/retry").status_code == 409  # only failed ones


def test_security_headers_and_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/does-not-exist").json()["error"]["code"] == "not_found"
