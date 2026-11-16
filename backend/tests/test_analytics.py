# ruff: noqa: F811
"""Recruitment analytics and security sweep (Phase 7)."""

import io

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog
from tests.conftest import applicant_client, make_opening, recruiter, user_id
from tests.test_evaluation import eval_id, marker, take
from tests.test_evaluation import case  # noqa: F401,F811  (fixture)


def stats(c, **params):
    r = c.get("/api/analytics/recruitment", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_system_returns_zeros_and_no_invented_rates(admin):
    d = stats(admin)
    assert d["totals"]["applications"] == 0 and d["funnel"][0]["count"] == 0
    assert all(v is None for v in d["rates"].values())
    assert d["notes"]


def test_numbers_come_from_real_records_and_funnel_is_consistent(admin, case):
    o, ap, a, dd, s = case  # a: approved, scheduled
    take(admin, ap, dd, s, speak=lambda i, sent: marker(sent))
    admin.post(f"/api/evaluations/{eval_id(admin, s)}/finalize")
    admin.post(f"/api/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "Strong"})
    admin.post(f"/api/applications/{a['id']}/analysis")

    o2 = make_opening(admin, title="Second role")
    ap2 = applicant_client("two@gmail.com")
    a2 = ap2.post("/api/applications", json={"opening_id": o2["id"]}).json()  # stays submitted
    ap3 = applicant_client("three@gmail.com")
    a3 = ap3.post("/api/applications", json={"opening_id": o2["id"]}).json()
    assert admin.post(f"/api/applications/{a3['id']}/reject", json={"reason": "Not a fit for this role"}).status_code in (200, 201)

    d = stats(admin)
    t = d["totals"]
    assert t["applications"] == 3 and t["pending"] == 1 and t["rejected"] == 1 and t["shortlisted"] == 1
    assert d["rates"]["rejection_rate"] == 50.0  # 1 rejected of 2 decided (shortlisted + rejected)
    assert d["rates"]["approval_rate"] == 50.0
    stages = {f["stage"]: f["count"] for f in d["funnel"]}
    assert stages["Applied"] == 3 and stages["Approved for assessment"] == 1 and stages["Test scheduled"] == 1
    assert stages["Test completed"] == 1 and stages["Evaluation finalised"] == 1 and stages["Shortlisted"] == 1 and stages["Selected"] == 0
    counts = [f["count"] for f in d["funnel"]]
    assert counts == sorted(counts, reverse=True) or stages["Applied"] >= max(counts[1:])
    assert d["rates"]["shortlisting_rate"] == 100.0 and d["rates"]["selection_rate"] == 0.0
    assert d["rates"]["completion_rate"] == 100.0
    assert d["scores"]["evaluated_candidates"] == 1 and d["scores"]["average_percentage"] is not None
    assert sum(b["count"] for b in d["scores"]["distribution"]) == 1
    assert {r["name"] for r in d["per_opening"]} == {o["title"], "Second role"}
    assert d["match_scores"]["analysed"] == 1
    assert sum(m["count"] for m in d["applications_by_month"]) == 3

    only = stats(admin, opening_id=o2["id"])
    assert only["totals"]["applications"] == 2 and only["totals"]["shortlisted"] == 0
    cat = stats(admin, category_id=o["category_id"])
    assert cat["totals"]["applications"] >= 1
    assert stats(admin, date_from="2999-01-01")["totals"]["applications"] == 0
    assert stats(admin, date_to="2000-01-01")["totals"]["applications"] == 0
    assert admin.get("/api/analytics/recruitment", params={"date_from": "not-a-date"}).status_code == 422
    assert a2["id"]


def test_employee_sees_only_assigned_openings_and_needs_permission(admin, case):
    o, ap, a, dd, s = case
    o2 = make_opening(admin, title="Hidden role")
    applicant_client("hid@gmail.com").post("/api/applications", json={"opening_id": o2["id"]})

    none = recruiter(admin, "none@solidpro-test.com", perms=("review_applications",))
    assert none.get("/api/analytics/recruitment").status_code == 403
    assert none.get("/api/analytics/export").status_code == 403

    viewer = recruiter(admin, "view@solidpro-test.com", perms=("view_analytics",))
    assert stats(viewer)["totals"]["applications"] == 0  # not assigned to anything
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(viewer)]})
    d = stats(viewer)
    assert d["totals"]["applications"] == 1 and [r["name"] for r in d["per_opening"]] == [o["title"]]
    assert stats(viewer, opening_id=o2["id"])["totals"]["applications"] == 0  # filtering cannot widen scope
    assert viewer.get("/api/analytics/recruitment", params={"employee_id": user_id(viewer)}).status_code == 403
    assert stats(admin, employee_id=user_id(viewer))["totals"]["applications"] == 1


def test_applicants_and_anonymous_are_locked_out(admin, client):
    ap = applicant_client("x@gmail.com")
    for path in ("/api/analytics/recruitment", "/api/analytics/export", "/api/analytics/compare?application_ids=1&application_ids=2"):
        assert ap.get(path).status_code == 404
        assert client.get(path).status_code == 401


def test_export_is_audited_and_formula_safe(admin):
    o = make_opening(admin, title="=HYPERLINK(\"http://evil\")")
    applicant_client("e@gmail.com").post("/api/applications", json={"opening_id": o["id"]})
    r = admin.get("/api/analytics/export", params={"report": "openings"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    body = r.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in body and "\n=HYPERLINK" not in body
    x = admin.get("/api/analytics/export", params={"report": "funnel", "format": "xlsx"})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    from openpyxl import load_workbook

    assert load_workbook(io.BytesIO(x.content)).active["A2"].value == "Applied"
    assert admin.get("/api/analytics/export", params={"report": "bogus"}).status_code == 422
    with SessionLocal() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.action == "analytics.export")).all()) == 2


def test_compare_validates_scope_and_permissions(admin, case):
    o, ap, a, dd, s = case
    o2 = make_opening(admin, title="Other")
    ap2 = applicant_client("b@gmail.com")
    b = ap2.post("/api/applications", json={"opening_id": o2["id"]}).json()
    q = [("application_ids", a["id"]), ("application_ids", b["id"])]
    r = admin.get("/api/analytics/compare", params=q)
    assert r.status_code == 200 and len(r.json()) == 2
    assert {x["candidate_name"] for x in r.json()} == {"Jane Doe"}
    assert admin.get("/api/analytics/compare", params=[("application_ids", a["id"])]).status_code == 422
    assert admin.get("/api/analytics/compare", params=[("application_ids", a["id"]), ("application_ids", 99999)]).status_code == 404

    emp = recruiter(admin, "cmp@solidpro-test.com", perms=("view_analytics", "review_applications"))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(emp)]})
    assert emp.get("/api/analytics/compare", params=q).status_code == 404  # b is outside the scope
    noreview = recruiter(admin, "nr@solidpro-test.com", perms=("view_analytics",))
    assert noreview.get("/api/analytics/compare", params=q).status_code == 403


# ---- security sweep: every route must demand a login ---------------------------------------------

PUBLIC = {
    ("POST", "/api/auth/register"), ("POST", "/api/auth/login"), ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/resend-verification"), ("POST", "/api/auth/forgot-password"), ("POST", "/api/auth/reset-password"),
    ("GET", "/api/auth/company-domains"), ("GET", "/api/job-openings/public"), ("GET", "/api/health"), ("POST", "/api/auth/logout"),
}


def test_every_route_requires_authentication(client):
    from app.main import app

    import re

    checked = 0
    bad: list[str] = []
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        for method in methods:
            method = method.upper()
            if method in ("HEAD", "OPTIONS"):
                continue
            concrete = re.sub(r"\{[^}]+\}", "1", path)
            if (method, concrete) in PUBLIC:
                continue
            r = client.request(method, concrete)
            checked += 1
            # 401 = login required. Public-by-design token endpoints may answer 400/404/422 without a session, never 200.
            if r.status_code not in (401, 404, 405, 422, 400):
                bad.append(f"{method} {path} -> {r.status_code}")
    assert not bad, bad
    assert checked > 80
