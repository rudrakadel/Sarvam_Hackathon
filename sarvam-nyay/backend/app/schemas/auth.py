"""
VeriDictum AI — Auth Pydantic Schemas
Request/response models for authentication endpoints.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator
from email_validator import validate_email as _validate_email, EmailNotValidError


def _validated_email(v: str) -> str:
    """Validate email without checking DNS deliverability."""
    try:
        result = _validate_email(v, check_deliverability=False)
        return result.normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    organisation_name: str

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validated_email(v)

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty.")
        return v.strip()


class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None    # Required if MFA is enabled

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validated_email(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                    # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validated_email(v)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        return v


class EnableMFAResponse(BaseModel):
    secret: str
    qr_code_base64: str         # PNG data URI for QR display
    totp_uri: str


class ConfirmMFARequest(BaseModel):
    totp_code: str


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]     # Shown once on MFA setup


class RevokeSessionRequest(BaseModel):
    session_id: UUID
