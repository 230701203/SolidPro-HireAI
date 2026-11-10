from datetime import timedelta

from fastapi import BackgroundTasks, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import (
    AccountStatus,
    CandidateProfile,
    CompanyEmailDomain,
    EmailVerificationToken,
    EmployeeProfile,
    PasswordResetToken,
    Role,
    User,
)
from app.models.base import utcnow
from app.schemas.auth import RegisterRequest
from app.services import audit_service, email_service, notification_service


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_company_email(db: Session, email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return (
        db.scalar(
            select(CompanyEmailDomain.id).where(CompanyEmailDomain.domain == domain, CompanyEmailDomain.is_active)
        )
        is not None
    )


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


# ---------------------------------------------------------------- registration & verification


def register(db: Session, data: RegisterRequest, background: BackgroundTasks, request: Request) -> User:
    email = normalize_email(data.email)
    if get_user_by_email(db, email):
        raise AppError(409, "email_taken", "An account with this email already exists.")

    is_employee = is_company_email(db, email)
    if not is_employee and not data.mobile:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"mobile": "Mobile number is required"})

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        mobile=data.mobile,
        role=Role.EMPLOYEE if is_employee else Role.APPLICANT,
        status=AccountStatus.PENDING_EMAIL_VERIFICATION,
        consent_accepted_at=utcnow(),
    )
    if is_employee:
        user.employee_profile = EmployeeProfile()
    else:
        user.candidate_profile = CandidateProfile()
    db.add(user)
    db.flush()

    send_verification_email(db, user, background)
    audit_service.log_action(
        db, "auth.register", entity_type="user", entity_id=user.id, details={"role": user.role.value}, request=request
    )
    db.commit()
    return user


def send_verification_email(db: Session, user: User, background: BackgroundTasks) -> None:
    s = get_settings()
    db.execute(
        delete(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None)
        )
    )
    raw, hashed = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(hours=s.email_verification_expire_hours),
        )
    )
    link = f"{s.frontend_url.rstrip('/')}/verify-email?token={raw}"
    extra = (
        ["After verification, an administrator must approve your account before you can sign in."]
        if user.role == Role.EMPLOYEE
        else []
    )
    email_service.queue_email(
        db,
        background,
        to_email=user.email,
        subject=f"Verify your email for {s.app_name}",
        template="verify_email",
        title="Verify your email address",
        paragraphs=[
            f"Hello {user.full_name},",
            f"Please confirm your email address to finish creating your {s.app_name} account. "
            f"This link expires in {s.email_verification_expire_hours} hours.",
            *extra,
        ],
        button=("Verify email", link),
        user_id=user.id,
    )


def verify_email(db: Session, raw_token: str, background: BackgroundTasks, request: Request) -> User:
    token = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(raw_token)))
    if token is None:
        raise AppError(400, "invalid_token", "This verification link is not valid.")
    user = db.get(User, token.user_id)
    assert user is not None

    if token.used_at is not None:
        # Idempotent: opening the link twice (or a prefetch) is harmless.
        if user.email_verified_at is not None:
            return user
        raise AppError(400, "invalid_token", "This verification link is not valid.")
    if token.expires_at < utcnow():
        raise AppError(400, "token_expired", "This verification link has expired. Please request a new one.")

    now = utcnow()
    token.used_at = now
    user.email_verified_at = now

    if user.status == AccountStatus.PENDING_EMAIL_VERIFICATION:
        if user.role == Role.EMPLOYEE:
            user.status = AccountStatus.PENDING_APPROVAL
            notification_service.notify_admins(
                db,
                background,
                type_="employee_registration",
                title="New employee registration",
                message=f"{user.full_name} ({user.email}) verified their email and is waiting for approval.",
                link="/admin/employees",
                email_subject="New employee registration awaiting approval",
                email_button=("Review request", f"{get_settings().frontend_url.rstrip('/')}/admin/employees"),
            )
        else:
            user.status = AccountStatus.ACTIVE
            notification_service.notify_admins(
                db,
                None,
                type_="applicant_registration",
                title="New applicant registered",
                message=f"{user.full_name} ({user.email}) created an applicant account.",
                link="/admin/users",
            )
            notification_service.notify(
                db, user.id, "welcome", "Welcome to SolidPro HireAI", "Your email is verified. Complete your profile to start applying."
            )
    audit_service.log_action(db, "auth.verify_email", entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return user


def resend_verification(db: Session, email: str, background: BackgroundTasks) -> None:
    """Always succeeds silently so the endpoint cannot be used to discover accounts."""
    user = get_user_by_email(db, email)
    if user and user.status == AccountStatus.PENDING_EMAIL_VERIFICATION:
        send_verification_email(db, user, background)
        db.commit()


# ---------------------------------------------------------------- login


def authenticate(db: Session, email: str, password: str, request: Request) -> User:
    s = get_settings()
    user = get_user_by_email(db, email)

    if user and user.locked_until and user.locked_until > utcnow():
        raise AppError(429, "account_locked", "Too many failed attempts. Try again in a few minutes.")

    if not verify_password(password, user.password_hash if user else None) or user is None:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= s.max_failed_logins:
                user.locked_until = utcnow() + timedelta(minutes=s.lockout_minutes)
                user.failed_login_attempts = 0
                audit_service.log_action(db, "auth.account_locked", actor=user, entity_type="user", entity_id=user.id, request=request)
            db.commit()
        raise AppError(401, "invalid_credentials", "Invalid email or password.")

    # Correct password: now it is safe to tell the user why they cannot sign in.
    blocked = {
        AccountStatus.PENDING_EMAIL_VERIFICATION: ("email_not_verified", "Please verify your email address first. Check your inbox for the verification link."),
        AccountStatus.PENDING_APPROVAL: ("pending_approval", "Your registration is waiting for administrator approval. You will receive an email once it is reviewed."),
        AccountStatus.REJECTED: ("account_rejected", "Your registration was not approved. Contact HR support for details."),
        AccountStatus.SUSPENDED: ("account_suspended", "Your account has been suspended. Contact an administrator."),
        AccountStatus.DEACTIVATED: ("account_deactivated", "Your account has been deactivated. Contact an administrator."),
    }
    if user.status in blocked:
        code, message = blocked[user.status]
        raise AppError(403, code, message)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    audit_service.log_action(db, "auth.login", actor=user, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return user


# ---------------------------------------------------------------- passwords


def request_password_reset(db: Session, email: str, background: BackgroundTasks, request: Request) -> None:
    """Always succeeds silently (no account enumeration)."""
    user = get_user_by_email(db, email)
    if user is None or user.status in (AccountStatus.REJECTED, AccountStatus.DEACTIVATED):
        return
    send_password_reset_email(db, user, background)
    audit_service.log_action(db, "auth.password_reset_requested", entity_type="user", entity_id=user.id, request=request)
    db.commit()


def send_password_reset_email(db: Session, user: User, background: BackgroundTasks, *, initiated_by_admin: bool = False) -> None:
    s = get_settings()
    db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    raw, hashed = generate_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(minutes=s.password_reset_expire_minutes),
        )
    )
    link = f"{s.frontend_url.rstrip('/')}/reset-password?token={raw}"
    who = "An administrator started a password reset for your account." if initiated_by_admin else "We received a request to reset your password."
    email_service.queue_email(
        db,
        background,
        to_email=user.email,
        subject=f"Reset your {s.app_name} password",
        template="password_reset",
        title="Reset your password",
        paragraphs=[
            f"Hello {user.full_name},",
            f"{who} This link expires in {s.password_reset_expire_minutes} minutes. "
            "If you did not expect this, you can ignore this email.",
        ],
        button=("Choose a new password", link),
        user_id=user.id,
    )


def reset_password(db: Session, raw_token: str, new_password: str, request: Request) -> User:
    token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token)))
    if token is None or token.used_at is not None:
        raise AppError(400, "invalid_token", "This reset link is not valid or has already been used.")
    if token.expires_at < utcnow():
        raise AppError(400, "token_expired", "This reset link has expired. Please request a new one.")
    user = db.get(User, token.user_id)
    assert user is not None
    try:
        validate_password_strength(new_password, email=user.email)
    except ValueError as exc:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"new_password": str(exc)}) from exc

    token.used_at = utcnow()
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    audit_service.log_action(db, "auth.password_reset", actor=user, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str, request: Request) -> User:
    if not verify_password(current_password, user.password_hash):
        raise AppError(400, "wrong_password", "Your current password is incorrect.", fields={"current_password": "Incorrect password"})
    if current_password == new_password:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"new_password": "New password must be different from the current one"})
    try:
        validate_password_strength(new_password, email=user.email)
    except ValueError as exc:
        raise AppError(422, "validation_error", "Please correct the highlighted fields.", fields={"new_password": str(exc)}) from exc
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.token_version += 1  # signs out every other session
    audit_service.log_action(db, "auth.password_changed", actor=user, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return user
