"""Stricter mobile and profile input rules."""

from datetime import date

import pytest

from app.core.security import validate_mobile
from tests.conftest import applicant_client


@pytest.mark.parametrize("value,expected", [
    ("+91 98765 43210", "+91 9876543210"), ("9876543210", "+91 9876543210"), ("+91-98765-43210", "+91 9876543210"),
    ("+1 415 555 0132", "+1 415 555 0132"), ("+971 50 123 4567", "+971 50 123 4567"),
])
def test_valid_mobiles_are_normalised(value, expected):
    assert validate_mobile(value) == expected


@pytest.mark.parametrize("value", [
    "987654321",            # 9 digits, no country code
    "+91 987654321",        # 9 digits after +91
    "+91 98765432101",      # 11 digits after +91
    "+91 1234567890",       # Indian numbers start 6-9
    "+91 9999999999",       # one repeated digit
    "+1 12345",             # too short overall
    "+1234567890123456",    # more than 15 digits
    "+0 12345678",          # country code cannot start with 0
    "98765abcde", "++919876543210", "",
])
def test_invalid_mobiles_are_refused(value):
    with pytest.raises(ValueError):
        validate_mobile(value)


def test_mobile_rule_applies_to_account_update(admin):
    me = applicant_client("mob@gmail.com")
    assert me.patch("/api/auth/me", json={"mobile": "987654321"}).status_code == 422
    r = me.patch("/api/auth/me", json={"mobile": "98765 43210"})
    assert r.status_code == 200 and r.json()["mobile"] == "+91 9876543210"


GOOD = {"city": "Chennai", "country": "India", "date_of_birth": "2000-05-04", "linkedin_url": "https://www.linkedin.com/in/dev",
        "github_url": "https://github.com/dev", "education": [{"degree": "B.E.", "institution": "REC", "graduation_year": 2024, "grade": "8.5 CGPA"}]}


def put(client, **over):
    return client.put("/api/applicants/profile", json={**GOOD, **over})


def test_profile_accepts_good_values(admin):
    assert put(applicant_client("ok@gmail.com")).status_code == 200


@pytest.mark.parametrize("over,field", [
    ({"date_of_birth": date.today().isoformat()}, "date_of_birth"),
    ({"date_of_birth": "1925-01-01"}, "date_of_birth"),
    ({"linkedin_url": "https://example.com/in/dev"}, "linkedin_url"),
    ({"github_url": "https://notgithub.com/dev"}, "github_url"),
    ({"linkedin_url": "https://localhost/x"}, "linkedin_url"),
    ({"city": "12345"}, "city"),
    ({"city": "Chennai<script>"}, "city"),
    ({"education": [{"degree": "B.E.", "institution": "REC", "graduation_year": 1960}]}, None),
    ({"education": [{"degree": "B.E.", "institution": "REC", "graduation_year": date.today().year + 20}]}, None),
    ({"education": [{"degree": "B.E.", "institution": "REC", "grade": "excellent"}]}, None),
    ({"education": [{"degree": "B.E.", "institution": "REC", "grade": "150%"}]}, None),
])
def test_profile_rejects_bad_values(admin, over, field):
    r = put(applicant_client("bad@gmail.com"), **over)
    assert r.status_code == 422, r.text
    if field:
        assert field in r.json()["error"]["fields"]


def test_other_hosts_and_grade_formats(admin):
    c = applicant_client("fmt@gmail.com")
    assert put(c, linkedin_url="https://in.linkedin.com/in/dev", portfolio_url="https://my.site/x").status_code == 200
    for g in ("72%", "8.5/10", "3.4 GPA", "8"):
        assert put(c, education=[{"degree": "B.E.", "institution": "REC", "grade": g}]).status_code == 200
