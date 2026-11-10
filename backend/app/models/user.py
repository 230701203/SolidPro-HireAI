import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.models.base import Base, JSONType, TimestampMixin, enum_column


class Role(str, enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"
    APPLICANT = "applicant"


class AccountStatus(str, enum.Enum):
    PENDING_EMAIL_VERIFICATION = "pending_email_verification"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_role_status", "role", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    mobile: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[Role] = mapped_column(enum_column(Role, "user_role", 20))
    status: Mapped[AccountStatus] = mapped_column(enum_column(AccountStatus, "account_status", 32))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false(), nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Incremented on password change/reset and suspension to invalidate issued tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    employee_profile: Mapped["EmployeeProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    candidate_profile: Mapped["CandidateProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class EmployeeProfile(TimestampMixin, Base):
    __tablename__ = "employee_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    department: Mapped[str | None] = mapped_column(String(100))
    designation: Mapped[str | None] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="employee_profile")


class CandidateProfile(TimestampMixin, Base):
    """Created with every applicant account. Detailed fields are added in Phase 2."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    user: Mapped[User] = relationship(back_populates="candidate_profile")


class EmployeeApproval(Base):
    """History of approve/reject decisions for employee registrations."""

    __tablename__ = "employee_approvals"
    __table_args__ = (Index("ix_employee_approvals_employee_id", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[ApprovalDecision] = mapped_column(enum_column(ApprovalDecision, "approval_decision", 16))
    reason: Mapped[str | None] = mapped_column(Text)
    permissions_granted: Mapped[list | None] = mapped_column(JSONType)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
