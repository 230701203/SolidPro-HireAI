from sqlalchemy import select

from app.core.config import get_settings
from app.database import SessionLocal
from app.models import AccountStatus, AuditLog, EmailLog, Role, User
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_NEW_PW,
    STRONG_PW,
    latest_token,
    login,
    make_admin_client,
    new_client,
    register,
    verify,
)


def _user(email: str) -> User:
    from sqlalchemy.orm import selectinload

    with SessionLocal() as db:
        return db.scalar(
            select(User)
            .options(selectinload(User.candidate_profile), selectinload(User.employee_profile))
            .where(User.email == email)
        )


# ------------------------------------------------------------------ admin bootstrap


def test_admin_forced_password_change(client):
    r = login(client, ADMIN_EMAIL, "InitialAdmin#2026")
    assert r.status_code == 200
    assert r.json()["role"] == "admin" and r.json()["must_change_password"] is True

    # Everything except /me and change-password is blocked until the password is changed.
    assert client.get("/api/auth/me").status_code == 200
    blocked = client.get("/api/users")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/api/dashboard/summary").status_code == 403

    r = client.post("/api/auth/change-password", json={"current_password": "InitialAdmin#2026", "new_password": ADMIN_NEW_PW})
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert client.get("/api/users").status_code == 200  # same session keeps working

    # Old password no longer works, new one does.
    assert login(new_client(), ADMIN_EMAIL, "InitialAdmin#2026").status_code == 401
    assert login(new_client(), ADMIN_EMAIL, ADMIN_NEW_PW).status_code == 200


def test_bootstrap_is_idempotent_and_does_not_reset_admin_password(admin):
    from app import cli

    cli.bootstrap()
    cli.bootstrap()
    assert login(new_client(), ADMIN_EMAIL, ADMIN_NEW_PW).status_code == 200
    with SessionLocal() as db:
        assert len(db.scalars(select(User).where(User.role == Role.ADMIN)).all()) == 1


def test_password_hash_is_argon2_and_never_returned(client):
    r = login(client, ADMIN_EMAIL, "InitialAdmin#2026")
    assert "password_hash" not in r.text and "argon2" not in r.text
    assert _user(ADMIN_EMAIL).password_hash.startswith("$argon2")


# ------------------------------------------------------------------ applicant registration


def test_applicant_registration_and_login_flow(client):
    r = register(client, "jane@gmail.com", name="Jane Doe")
    assert r.status_code == 201
    u = _user("jane@gmail.com")
    assert u.role == Role.APPLICANT and u.status == AccountStatus.PENDING_EMAIL_VERIFICATION
    assert u.candidate_profile is not None
    assert u.consent_accepted_at is not None

    # Cannot log in before verifying.
    r = login(client, "jane@gmail.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"

    r = verify(client, "jane@gmail.com")
    assert r.status_code == 200 and r.json()["status"] == "active"

    r = login(client, "jane@gmail.com")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "applicant" and body["permissions"] == []
    assert "hireai_session" in r.cookies or "hireai_session" in client.cookies
    assert client.get("/api/auth/me").json()["email"] == "jane@gmail.com"


def test_registration_stores_only_token_hash_and_logs_email(client):
    register(client, "tok@gmail.com")
    raw = latest_token("tok@gmail.com", "verify_email")
    with SessionLocal() as db:
        from app.models import EmailVerificationToken

        row = db.scalars(select(EmailVerificationToken)).first()
        assert row.token_hash != raw and len(row.token_hash) == 64
        log = db.scalars(select(EmailLog).where(EmailLog.to_email == "tok@gmail.com")).first()
        # No SMTP configured in tests -> honestly recorded as dev_logged, never "sent".
        assert log.status.value == "dev_logged"


def test_verify_email_is_idempotent_and_rejects_garbage(client):
    register(client, "twice@gmail.com")
    assert verify(client, "twice@gmail.com").status_code == 200
    assert verify(client, "twice@gmail.com").status_code == 200  # link opened twice
    r = client.post("/api/auth/verify-email", json={"token": "x" * 30})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"


def test_duplicate_email_rejected_case_insensitively(client):
    assert register(client, "dup@gmail.com").status_code == 201
    r = register(client, "DUP@Gmail.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_registration_validation(client):
    r = register(client, "weak@gmail.com", password="short")
    assert r.status_code == 422 and "password" in r.json()["error"]["fields"]
    r = register(client, "terms@gmail.com", terms=False)
    assert r.status_code == 422 and "accept_terms" in r.json()["error"]["fields"]
    r = register(client, "nomobile@gmail.com", mobile=None)
    assert r.status_code == 422 and "mobile" in r.json()["error"]["fields"]
    r = register(client, "badmobile@gmail.com", mobile="abc")
    assert r.status_code == 422 and "mobile" in r.json()["error"]["fields"]
    r = client.post("/api/auth/register", json={"full_name": "X Y", "email": "not-an-email", "password": STRONG_PW, "accept_terms": True})
    assert r.status_code == 422 and "email" in r.json()["error"]["fields"]


def test_invalid_login_is_generic_and_does_not_leak_accounts(client):
    register(client, "real@gmail.com")
    verify(client, "real@gmail.com")
    a = login(client, "real@gmail.com", "WrongPassw0rd!")
    b = login(client, "ghost@gmail.com", "WrongPassw0rd!")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_lockout_after_repeated_failures(client):
    register(client, "lock@gmail.com")
    verify(client, "lock@gmail.com")
    for _ in range(get_settings().max_failed_logins):
        assert login(client, "lock@gmail.com", "WrongPassw0rd!").status_code == 401
    r = login(client, "lock@gmail.com", STRONG_PW)  # even the right password is refused while locked
    assert r.status_code == 429 and r.json()["error"]["code"] == "account_locked"


def test_remember_me_sets_persistent_cookie(client):
    register(client, "rem@gmail.com")
    verify(client, "rem@gmail.com")
    r1 = login(new_client(), "rem@gmail.com", remember_me=False)
    r2 = login(new_client(), "rem@gmail.com", remember_me=True)
    assert "max-age" not in r1.headers["set-cookie"].lower()
    assert "max-age=" in r2.headers["set-cookie"].lower()
    assert "httponly" in r2.headers["set-cookie"].lower()


def test_logout_clears_session(client):
    register(client, "out@gmail.com")
    verify(client, "out@gmail.com")
    login(client, "out@gmail.com")
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_unauthenticated_requests_are_rejected():
    c = new_client()
    for path in ["/api/auth/me", "/api/users", "/api/employees", "/api/notifications", "/api/dashboard/summary", "/api/audit-logs"]:
        r = c.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "not_authenticated"


def test_tampered_token_rejected(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


# ------------------------------------------------------------------ password reset


def test_password_reset_flow_invalidates_sessions_and_token_is_single_use(client):
    register(client, "reset@gmail.com")
    verify(client, "reset@gmail.com")
    old_session = new_client()
    login(old_session, "reset@gmail.com")

    assert client.post("/api/auth/forgot-password", json={"email": "reset@gmail.com"}).status_code == 200
    token = latest_token("reset@gmail.com", "password_reset")

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "weak"})
    assert r.status_code == 422 and "new_password" in r.json()["error"]["fields"]

    new_pw = "BrandNewPassw0rd!"
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 400  # single use

    assert login(new_client(), "reset@gmail.com", STRONG_PW).status_code == 401
    assert login(new_client(), "reset@gmail.com", new_pw).status_code == 200
    assert old_session.get("/api/auth/me").status_code == 401  # previous session was revoked


def test_forgot_password_does_not_reveal_unknown_emails(client):
    a = client.post("/api/auth/forgot-password", json={"email": "nobody@gmail.com"})
    register(client, "known@gmail.com")
    verify(client, "known@gmail.com")
    b = client.post("/api/auth/forgot-password", json={"email": "known@gmail.com"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    with SessionLocal() as db:
        assert not db.scalars(select(EmailLog).where(EmailLog.to_email == "nobody@gmail.com")).first()


def test_expired_reset_token_rejected(client):
    register(client, "exp@gmail.com")
    verify(client, "exp@gmail.com")
    client.post("/api/auth/forgot-password", json={"email": "exp@gmail.com"})
    token = latest_token("exp@gmail.com", "password_reset")
    with SessionLocal() as db:
        from datetime import timedelta

        from app.models import PasswordResetToken
        from app.models.base import utcnow

        t = db.scalars(select(PasswordResetToken)).first()
        t.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "BrandNewPassw0rd!"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_expired"


def test_change_password_requires_correct_current_password(client):
    register(client, "chg@gmail.com")
    verify(client, "chg@gmail.com")
    login(client, "chg@gmail.com")
    r = client.post("/api/auth/change-password", json={"current_password": "Nope12345!!", "new_password": "AnotherPassw0rd!"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "wrong_password"


def test_update_profile(client):
    register(client, "prof@gmail.com")
    verify(client, "prof@gmail.com")
    login(client, "prof@gmail.com")
    r = client.patch("/api/auth/me", json={"full_name": "New Name", "mobile": "+911234567890"})
    assert r.status_code == 200 and r.json()["full_name"] == "New Name"
    assert client.patch("/api/auth/me", json={"mobile": "bad"}).status_code == 422


def test_rate_limiting_on_login(client):
    get_settings().rate_limit_enabled = True
    try:
        codes = [login(client, "x@gmail.com", "WrongPassw0rd!").status_code for _ in range(22)]
    finally:
        get_settings().rate_limit_enabled = False
    assert 429 in codes and codes[0] == 401


def test_audit_trail_created_for_auth_events(admin):
    with SessionLocal() as db:
        actions = {a.action for a in db.scalars(select(AuditLog)).all()}
    assert {"auth.login", "auth.password_changed"} <= actions
    assert make_admin_client  # fixture import sanity
