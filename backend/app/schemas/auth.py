import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator

from app.core.security import NAME_MAX, NAME_MIN, validate_email_quality, validate_full_name, validate_password_strength
from app.models import AccountStatus, Role

_MOBILE_RE = re.compile(r"^\+?[0-9][0-9 \-]{7,17}$")


def _clean_mobile(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _MOBILE_RE.match(value):
        raise ValueError("Enter a valid mobile number (8-15 digits, optional + prefix)")
    return value


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=NAME_MIN, max_length=NAME_MAX + 20)  # exact rules in the validator below
    email: EmailStr
    password: str
    mobile: str | None = None
    accept_terms: bool

    @field_validator("full_name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        return validate_full_name(v)

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        return validate_email_quality(v).lower()

    @field_validator("password")
    @classmethod
    def _password_ok(cls, v: str, info: ValidationInfo) -> str:
        return validate_password_strength(v, email=info.data.get("email"))  # email is validated first (field order)

    @field_validator("mobile")
    @classmethod
    def _mobile_ok(cls, v: str | None) -> str | None:
        return _clean_mobile(v)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the privacy and data-processing notice to register")
        return v


class LoginRequest(BaseModel):
    # Login only checks shape and length: it must never reject an existing account because the rules got stricter.
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.strip().lower()


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailOnlyRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_ok(cls, v: str) -> str:
        return validate_password_strength(v)


class UpdateMeRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=NAME_MIN, max_length=NAME_MAX + 20)
    mobile: str | None = None

    @field_validator("full_name")
    @classmethod
    def _name_ok(cls, v: str | None) -> str | None:
        return validate_full_name(v) if v is not None else None

    @field_validator("mobile")
    @classmethod
    def _mobile_ok(cls, v: str | None) -> str | None:
        return _clean_mobile(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    mobile: str | None
    role: Role
    status: AccountStatus
    must_change_password: bool
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    permissions: list[str] = []
    department: str | None = None
    designation: str | None = None


class VerifyEmailResult(BaseModel):
    status: AccountStatus
    role: Role
    message: str
