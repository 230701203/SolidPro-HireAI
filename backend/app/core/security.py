import hashlib
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta

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


PASSWORD_MIN, PASSWORD_MAX = 10, 64
SPECIAL_CHARS = "!@#$%^&*()_+-=[]{};':\",.<>/?\\|`~"
_COMMON = ("password", "qwerty", "123456", "letmein", "iloveyou", "welcome1", "admin123")
EMAIL_MAX, EMAIL_LOCAL_MAX = 254, 64
NAME_MIN, NAME_MAX = 2, 60
# Mirrors frontend/src/utils/validation.ts. The server stays the source of truth.
_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._%+\-]*[A-Za-z0-9])?$")
_DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?$")


def validate_email_quality(email: str) -> str:
    """Stricter than 'looks like an email': sane length and characters, a real-looking domain, no junk."""
    e = email.strip()
    if len(e) > EMAIL_MAX:
        raise ValueError(f"Email must be at most {EMAIL_MAX} characters")
    if " " in e or e.count("@") != 1:
        raise ValueError("Enter a valid email address such as name@company.com")
    local, domain = e.split("@")
    if not local or len(local) > EMAIL_LOCAL_MAX:
        raise ValueError(f"The part before @ must be 1 to {EMAIL_LOCAL_MAX} characters")
    if ".." in local or not _EMAIL_LOCAL_RE.match(local):
        raise ValueError("The part before @ may only use letters, numbers and . _ % + - (no leading, trailing or double dots)")
    if not re.search(r"[A-Za-z]", local):
        raise ValueError("The part before @ must contain at least one letter")
    labels = domain.split(".")
    if len(labels) < 2 or any(not lab or len(lab) > 63 or not _DOMAIN_LABEL_RE.match(lab) for lab in labels):
        raise ValueError("The domain after @ must look like company.com")
    if not re.fullmatch(r"[A-Za-z]{2,24}", labels[-1]):
        raise ValueError("The domain must end with a valid extension such as .com or .in")
    return e


def validate_mobile(value: str) -> str:
    """Normalise and check a mobile number. Mirrored by frontend/src/utils/mobile.ts: change both together.

    India (+91) must be exactly 10 digits starting 6-9. Other countries: 8 to 15 digits in total including the
    country code. Numbers made of one repeated digit (9999999999) are refused.
    """
    raw = re.sub(r"[ \-]+", " ", value.strip())
    if not re.fullmatch(r"\+?[0-9][0-9 ]*", raw):
        raise ValueError("Use digits only, with an optional + before the country code")
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+"):
        if len(digits) == 10:
            raw, digits = "+91 " + digits, "91" + digits
        else:
            raise ValueError("Include the country code, for example +91 98765 43210")
    if digits.startswith("91"):
        national = digits[2:]
        if len(national) != 10:
            raise ValueError("An Indian mobile number has exactly 10 digits after +91")
        if national[0] not in "6789":
            raise ValueError("An Indian mobile number starts with 6, 7, 8 or 9")
        raw = "+91 " + national
    else:
        if digits.startswith("0") or not 8 <= len(digits) <= 15:
            raise ValueError("Enter 8 to 15 digits including the country code")
        national = digits[-8:]
    if len(set(national)) == 1:
        raise ValueError("Enter a real mobile number")
    return raw


def validate_full_name(name: str) -> str:
    n = re.sub(r"\s+", " ", name.strip())
    if len(n) < NAME_MIN or len(n) > NAME_MAX:
        raise ValueError(f"Name must be {NAME_MIN} to {NAME_MAX} characters")
    # Letters of any language (including combining marks used in Indic scripts), spaces and . ' -
    ok_chars = all(c.isalpha() or unicodedata.category(c).startswith("M") or c in " .'-" for c in n)
    if not ok_chars or not n[0].isalpha() or sum(c.isalpha() for c in n) < NAME_MIN or re.search(r"[.'\-]{2,}", n):
        raise ValueError("Name may only contain letters, spaces and . ' - (and must start with a letter)")
    return n


def validate_password_strength(password: str, *, email: str | None = None) -> str:
    """Return the password if acceptable, else raise ValueError with a user-facing message."""
    if len(password) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters long")
    if len(password) > PASSWORD_MAX:
        raise ValueError(f"Password must be at most {PASSWORD_MAX} characters long")
    if any(c.isspace() for c in password):
        raise ValueError("Password must not contain spaces")
    if not all(c.isascii() and c.isprintable() for c in password):
        raise ValueError("Password may only use English letters, digits and symbols")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain an uppercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain a digit")
    if not any(c in SPECIAL_CHARS for c in password):
        raise ValueError("Password must contain a symbol such as ! @ # $ %")
    low = password.lower()
    if any(w in low for w in _COMMON):
        raise ValueError("Password is too easy to guess; avoid common words and sequences")
    if email:
        local = email.split("@")[0].lower()
        if low == email.lower() or (len(local) >= 6 and local in low):
            raise ValueError("Password must not contain your email name")
    return password


def create_access_token(user_id: int, token_version: int, *, remember_me: bool = False) -> tuple[str, int]:
    """Return (jwt, lifetime_seconds)."""
    s = get_settings()
    minutes = s.remember_me_expire_minutes if remember_me else s.access_token_expire_minutes
    now = datetime.now(UTC)
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
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*?"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            return validate_password_strength(pw)
        except ValueError:
            continue
