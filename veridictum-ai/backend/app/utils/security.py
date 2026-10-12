"""
VeriDictum AI — Security Utilities
JWT tokens, password hashing, TOTP, bcrypt backup codes.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pyotp
import qrcode
from io import BytesIO
from base64 import b64encode

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return bcrypt hash of plain-text password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain-text password against bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def validate_password_strength(password: str, min_length: int = 12) -> list[str]:
    """Return list of unmet password requirements (empty = valid)."""
    errors = []
    if len(password) < min_length:
        errors.append(f"At least {min_length} characters required.")
    if not any(c.isupper() for c in password):
        errors.append("At least one uppercase letter required.")
    if not any(c.islower() for c in password):
        errors.append("At least one lowercase letter required.")
    if not any(c.isdigit() for c in password):
        errors.append("At least one digit required.")
    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password):
        errors.append("At least one special character required.")
    return errors


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def create_access_token(subject: str, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "type": "access", "jti": str(uuid.uuid4())}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": str(uuid.uuid4())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and verify JWT; raises JWTError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def hash_token(token: str) -> str:
    """SHA-256 hash of a token string (for DB storage)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# TOTP / MFA
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    """Generate a new TOTP secret key."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, user_email: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user_email, issuer_name=settings.TOTP_ISSUER)


def generate_qr_code_base64(totp_uri: str) -> str:
    """Return base64-encoded PNG QR code for the TOTP URI."""
    img = qrcode.make(totp_uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return b64encode(buf.getvalue()).decode("utf-8")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code (allows ±1 window for clock drift)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate one-time backup codes (plain text — hash before storing)."""
    return [secrets.token_hex(5).upper() for _ in range(count)]


def hash_backup_codes(codes: list[str]) -> str:
    """Return JSON-encoded list of bcrypt-hashed backup codes."""
    return json.dumps([pwd_context.hash(c) for c in codes])


def verify_backup_code(plain: str, stored_json: str) -> tuple[bool, str]:
    """
    Check if plain code matches any stored hash.
    Returns (matched, updated_json) — the matched code is removed.
    """
    codes = json.loads(stored_json)
    for i, hashed in enumerate(codes):
        if pwd_context.verify(plain, hashed):
            codes.pop(i)
            return True, json.dumps(codes)
    return False, stored_json


# ---------------------------------------------------------------------------
# Secure token generation
# ---------------------------------------------------------------------------
def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(nbytes)
