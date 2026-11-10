"""Management commands.

    python -m app.cli bootstrap     # idempotent: permissions, company domains, initial admin
    python -m app.cli seed-dev      # development only: sample employee/applicant accounts
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import PERMISSIONS
from app.core.security import generate_password, hash_password, validate_password_strength
from app.database import SessionLocal
from app.models import (
    AccountStatus,
    CandidateProfile,
    CompanyEmailDomain,
    EmployeeProfile,
    Permission,
    Role,
    User,
)
from app.models.base import utcnow


def sync_permissions(db: Session) -> int:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    added = 0
    for code, description, category in PERMISSIONS:
        if code in existing:
            existing[code].description, existing[code].category = description, category
        else:
            db.add(Permission(code=code, description=description, category=category))
            added += 1
    db.flush()
    return added


def sync_domains(db: Session) -> int:
    s = get_settings()
    existing = {d.domain for d in db.scalars(select(CompanyEmailDomain)).all()}
    added = 0
    for domain in s.company_domain_list:
        if domain not in existing:
            db.add(CompanyEmailDomain(domain=domain, is_active=True))
            added += 1
    db.flush()
    return added


def ensure_admin(db: Session) -> tuple[User | None, str | None]:
    """Create the initial admin once. Returns (user, generated_password_or_None)."""
    s = get_settings()
    if not s.admin_email:
        print("ADMIN_EMAIL is not set; skipping admin creation.", file=sys.stderr)
        return None, None
    email = s.admin_email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        return None, None  # already exists; never overwrite credentials

    generated = None
    password = s.admin_initial_password
    if password:
        validate_password_strength(password, email=email)
    else:
        password = generated = generate_password()
    admin = User(
        email=email,
        password_hash=hash_password(password),
        full_name=s.admin_name,
        role=Role.ADMIN,
        status=AccountStatus.ACTIVE,
        must_change_password=True,  # forced change at first login
        email_verified_at=utcnow(),
        consent_accepted_at=utcnow(),
    )
    db.add(admin)
    db.flush()
    return admin, generated


def bootstrap() -> None:
    with SessionLocal() as db:
        perms = sync_permissions(db)
        domains = sync_domains(db)
        admin, generated = ensure_admin(db)
        db.commit()
    print(f"Permissions synced ({perms} new). Company domains added: {domains}.")
    if admin:
        print(f"Admin account created: {admin.email} (must change password at first login)")
        if generated:
            print("\n  Generated initial password (shown only once, store it securely):")
            print(f"  {generated}\n")
    else:
        print("Admin account already exists or ADMIN_EMAIL not set; nothing changed.")


def seed_dev() -> None:
    """Development-only sample data. Passwords are random and printed once; nothing is hardcoded."""
    s = get_settings()
    if s.is_production:
        sys.exit("Refusing to seed development data in production.")
    domain = (s.company_domain_list or ["solidpro.example"])[0]
    samples = [
        (f"dev.employee@{domain}", "Dev Employee", Role.EMPLOYEE, AccountStatus.PENDING_APPROVAL),
        (f"dev.reviewer@{domain}", "Dev Reviewer", Role.EMPLOYEE, AccountStatus.PENDING_APPROVAL),
        ("dev.applicant@example.com", "Dev Applicant", Role.APPLICANT, AccountStatus.ACTIVE),
    ]
    with SessionLocal() as db:
        sync_permissions(db)
        sync_domains(db)
        for email, name, role, status in samples:
            if db.scalar(select(User).where(User.email == email)):
                print(f"exists: {email}")
                continue
            pw = generate_password()
            user = User(
                email=email,
                password_hash=hash_password(pw),
                full_name=name,
                mobile="+910000000000" if role == Role.APPLICANT else None,
                role=role,
                status=status,
                email_verified_at=utcnow(),
                consent_accepted_at=utcnow(),
            )
            user.employee_profile = EmployeeProfile() if role == Role.EMPLOYEE else None
            user.candidate_profile = CandidateProfile() if role == Role.APPLICANT else None
            db.add(user)
            print(f"created: {email}  password: {pw}  status: {status.value}")
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["bootstrap", "seed-dev"])
    args = parser.parse_args()
    {"bootstrap": bootstrap, "seed-dev": seed_dev}[args.command]()


if __name__ == "__main__":
    main()
