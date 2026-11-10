"""Test fixtures. Tests run against a real PostgreSQL database (never the dev database).

Set TEST_DATABASE_URL, e.g. postgresql+psycopg://postgres@localhost:5432/hireai_test.
The schema is created by running the real Alembic migrations, so migrations are tested too.
"""

import os
import re

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5433/hireai_test")
os.environ.update(
    {
        "DATABASE_URL": TEST_DB_URL,
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "RATE_LIMIT_ENABLED": "false",
        "COMPANY_EMAIL_DOMAINS": "solidpro-test.com",
        "ADMIN_EMAIL": "admin@solidpro-test.com",
        "ADMIN_NAME": "Test Admin",
        "ADMIN_INITIAL_PASSWORD": "InitialAdmin#2026",
        "SMTP_HOST": "",
        "FRONTEND_URL": "http://localhost:5173",
    }
)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app import cli  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AccountStatus, EmailLog, Role, User  # noqa: E402
from app.models.base import utcnow  # noqa: E402

STRONG_PW = "Str0ngPassw0rd!"
ADMIN_EMAIL = "admin@solidpro-test.com"
ADMIN_NEW_PW = "AdminChanged#2026"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    limiter.reset()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE users, permissions, company_email_domains, notifications, email_logs, audit_logs "
                "RESTART IDENTITY CASCADE"
            )
        )
    cli.bootstrap()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def new_client() -> TestClient:
    return TestClient(app)


def latest_token(email: str, kind: str) -> str:
    """Extract the raw token from the most recent email of this kind sent to `email`."""
    with SessionLocal() as db:
        log = db.scalars(
            select(EmailLog).where(EmailLog.to_email == email, EmailLog.template == kind).order_by(EmailLog.id.desc())
        ).first()
        assert log is not None, f"no {kind} email for {email}"
        m = re.search(r"token=([A-Za-z0-9_\-]+)", log.body_text)
        assert m, log.body_text
        return m.group(1)


def register(c: TestClient, email: str, *, name="Test User", password=STRONG_PW, mobile="+919876543210", terms=True):
    return c.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": password, "mobile": mobile, "accept_terms": terms},
    )


def verify(c: TestClient, email: str):
    return c.post("/api/auth/verify-email", json={"token": latest_token(email, "verify_email")})


def login(c: TestClient, email: str, password: str = STRONG_PW, remember_me=False):
    return c.post("/api/auth/login", json={"email": email, "password": password, "remember_me": remember_me})


def make_admin_client() -> TestClient:
    """Log in as the bootstrapped admin and complete the forced password change."""
    c = new_client()
    r = login(c, ADMIN_EMAIL, "InitialAdmin#2026")
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    r = c.post("/api/auth/change-password", json={"current_password": "InitialAdmin#2026", "new_password": ADMIN_NEW_PW})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin():
    return make_admin_client()


def make_active_user(email: str, role: Role, *, password=STRONG_PW, name="Active User") -> User:
    from app.core.security import hash_password
    from app.models import CandidateProfile, EmployeeProfile

    with SessionLocal() as db:
        u = User(
            email=email, password_hash=hash_password(password), full_name=name, mobile="+919876543210", role=role,
            status=AccountStatus.ACTIVE, email_verified_at=utcnow(), consent_accepted_at=utcnow(),
        )
        if role == Role.EMPLOYEE:
            u.employee_profile = EmployeeProfile()
        if role == Role.APPLICANT:
            u.candidate_profile = CandidateProfile()
        db.add(u)
        db.commit()
        return u


def approved_employee(admin_client: TestClient, email="emp@solidpro-test.com", perms=("review_applications",)) -> TestClient:
    """Register, verify, approve and log in an employee. Returns the employee's client."""
    c = new_client()
    assert register(c, email, name="Emp Loyee", mobile=None).status_code == 201
    assert verify(c, email).status_code == 200
    emp_id = next(e["id"] for e in admin_client.get("/api/employees/pending").json() if e["email"] == email)
    r = admin_client.post(f"/api/employees/{emp_id}/approve", json={"permission_codes": list(perms)})
    assert r.status_code == 200, r.text
    assert login(c, email).status_code == 200
    return c
