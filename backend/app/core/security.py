import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

# Verified against when the account does not exist, so response time does not reveal valid emails.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str, *, email: str | None = None) -> str:
    """Return the password if acceptable, else raise ValueError with a user-facing message."""
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters long")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain an uppercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain a digit")
    if email and password.lower() == email.lower():
        raise ValueError("Password must not be the same as your email")
    return password


def create_access_token(user_id: int, token_version: int, *, remember_me: bool = False) -> tuple[str, int]:
    """Return (jwt, lifetime_seconds)."""
    s = get_settings()
    minutes = s.remember_me_expire_minutes if remember_me else s.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm), minutes * 60


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


def generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Only the hash is stored in the database."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_password(length: int = 18) -> str:
    """Random password that satisfies validate_password_strength."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            return validate_password_strength(pw)
        except ValueError:
            continue
