from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import PERMISSION_CODES
from app.models import AccountStatus, ApprovalDecision, EmailStatus, Role


def _check_codes(codes: list[str]) -> list[str]:
    unknown = sorted(set(codes) - PERMISSION_CODES)
    if unknown:
        raise ValueError(f"Unknown permission(s): {', '.join(unknown)}")
    return sorted(set(codes))


class ApproveEmployeeRequest(BaseModel):
    permission_codes: list[str] = []
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)

    _validate_codes = field_validator("permission_codes")(_check_codes)


class RejectEmployeeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class SetPermissionsRequest(BaseModel):
    permission_codes: list[str]

    _validate_codes = field_validator("permission_codes")(_check_codes)


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    description: str
    category: str


class ApprovalHistoryOut(BaseModel):
    decision: ApprovalDecision
    reason: str | None
    decided_by_name: str | None
    decided_at: datetime
    permissions_granted: list[str] | None


class EmployeeOut(BaseModel):
    id: int
    email: str
    full_name: str
    mobile: str | None
    status: AccountStatus
    created_at: datetime
    email_verified_at: datetime | None
    last_login_at: datetime | None
    department: str | None
    designation: str | None
    permissions: list[str]


class EmployeeDetailOut(EmployeeOut):
    approvals: list[ApprovalHistoryOut]


class UserListItem(BaseModel):
    id: int
    email: str
    full_name: str
    mobile: str | None
    role: Role
    status: AccountStatus
    created_at: datetime
    email_verified_at: datetime | None
    last_login_at: datetime | None


class SetStatusRequest(BaseModel):
    status: Literal["active", "suspended", "deactivated"]
    reason: str | None = Field(default=None, max_length=500)


class AuditLogOut(BaseModel):
    id: int
    created_at: datetime
    actor_id: int | None
    actor_name: str | None
    actor_email: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict | None
    ip_address: str | None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    title: str
    message: str
    link: str | None
    is_read: bool
    created_at: datetime


class EmailDomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    domain: str
    is_active: bool
    created_at: datetime


class EmailDomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=255)

    @field_validator("domain")
    @classmethod
    def _domain_ok(cls, v: str) -> str:
        import re

        v = v.strip().lower().removeprefix("@")
        if not re.match(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$", v):
            raise ValueError("Enter a valid domain such as company.com")
        return v


class EmailDomainUpdate(BaseModel):
    is_active: bool


class EmailLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    to_email: str
    subject: str
    template: str
    status: EmailStatus
    attempts: int
    error: str | None
    created_at: datetime
    sent_at: datetime | None
