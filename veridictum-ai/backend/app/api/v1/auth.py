"""
VeriDictum AI — Auth API Router
Handles registration, login, MFA, token refresh, password reset (UC-01 through UC-12).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, get_redis, rate_limit
from app.models import (
    AccountStatus,
    Invitation,
    Organisation,
    RefreshToken,
    SubscriptionTier,
    User,
    UserRole,
)
from app.schemas.auth import (
    BackupCodesResponse,
    ConfirmMFARequest,
    EnableMFAResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.utils.email import (
    send_password_reset_email,
    send_verification_email,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    generate_backup_codes,
    generate_qr_code_base64,
    generate_secure_token,
    generate_totp_secret,
    get_totp_uri,
    hash_backup_codes,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_backup_code,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
) -> dict:
    """UC-01: Register a new attorney account."""
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Create organisation
    org = Organisation(
        name=body.organisation_name,
        subscription_tier=SubscriptionTier.STARTER,
    )
    db.add(org)
    await db.flush()

    # Create user — set ACTIVE immediately (email verification is optional in dev)
    verify_token = generate_secure_token()
    user = User(
        organisation_id=org.id,
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
        email_verify_token=verify_token,
        email_verify_token_expiry=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Send verification email in background (non-blocking — silently ignored if SMTP unavailable)
    background_tasks.add_task(
        send_verification_email, user.email, user.full_name, verify_token
    )

    return {
        "message": "Registration successful.",
        "user_id": str(user.id),
    }


# ---------------------------------------------------------------------------
# Verify Email
# ---------------------------------------------------------------------------
@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """UC-01: Verify email address with token."""
    result = await db.execute(
        select(User).where(User.email_verify_token == body.token)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token.")
    expiry = user.email_verify_token_expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry and expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification token expired. Please request a new one.")

    user.email_verified = True
    user.status = AccountStatus.ACTIVE
    user.email_verify_token = None
    user.email_verify_token_expiry = None
    return {"message": "Email verified successfully. You can now log in."}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _: None = Depends(rate_limit),
) -> TokenResponse:
    """UC-02: Email/password login with optional MFA."""
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    credentials_error = HTTPException(status_code=401, detail="Invalid credentials.")

    if not user or not user.hashed_password:
        raise credentials_error

    # Check lockout
    lockout = user.lockout_until
    if lockout and lockout.tzinfo is None:
        lockout = lockout.replace(tzinfo=timezone.utc)
    if lockout and lockout > datetime.now(timezone.utc):
        remaining = int((lockout - datetime.now(timezone.utc)).total_seconds() / 60)
        raise HTTPException(status_code=423, detail=f"Account locked. Try again in {remaining} minutes.")

    # Verify password
    if not verify_password(body.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            user.status = AccountStatus.LOCKED
        raise credentials_error

    # Check account status
    if user.status not in (AccountStatus.ACTIVE,):
        raise HTTPException(status_code=403, detail=f"Account is {user.status.value.lower()}.")

    # TOTP check
    if user.mfa_enabled:
        if not body.totp_code:
            raise HTTPException(status_code=200, detail="MFA_REQUIRED")
        if not verify_totp(user.mfa_secret, body.totp_code):
            raise HTTPException(status_code=401, detail="Invalid MFA code.")

    # Reset failed attempts
    user.failed_login_attempts = 0
    user.lockout_until = None
    user.last_login = datetime.now(timezone.utc)

    # Issue tokens
    access_token = create_access_token(str(user.id), {"role": user.role, "org": str(user.organisation_id)})
    refresh_token = create_refresh_token(str(user.id))

    # Persist refresh token
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        device_info=request.headers.get("User-Agent", "")[:255],
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    ))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=900,
    )


# ---------------------------------------------------------------------------
# Refresh Token
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Rotate refresh token and issue new access token."""
    from jose import JWTError
    from app.utils.security import decode_token

    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")
        user_id = payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    expires = stored.expires_at
    # If stored datetime is naive, make it aware (UTC)
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not stored or (expires and expires < now):
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked.")

    # Revoke old, issue new
    stored.is_revoked = True

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    new_access = create_access_token(str(user.id), {"role": user.role, "org": str(user.organisation_id)})
    new_refresh = create_refresh_token(str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    ))

    return TokenResponse(access_token=new_access, refresh_token=new_refresh, expires_in=900)


# ---------------------------------------------------------------------------
# Forgot / Reset Password
# ---------------------------------------------------------------------------
@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
) -> dict:
    """UC-06: Send password reset email (always returns generic message to prevent enumeration)."""
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user and user.status != AccountStatus.DEACTIVATED:
        token = generate_secure_token()
        user.password_reset_token = hash_token(token)
        user.password_reset_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        background_tasks.add_task(send_password_reset_email, user.email, user.full_name, token)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """UC-06: Reset password with token."""
    token_hash = hash_token(body.token)
    result = await db.execute(
        select(User).where(User.password_reset_token == token_hash)
    )
    user = result.scalar_one_or_none()
    reset_expiry = user.password_reset_expiry if user else None
    if reset_expiry and reset_expiry.tzinfo is None:
        reset_expiry = reset_expiry.replace(tzinfo=timezone.utc)
    if not user or not reset_expiry or reset_expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_expiry = None
    user.last_password_change = datetime.now(timezone.utc)

    # Revoke all refresh tokens
    tokens = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    for t in tokens.scalars():
        t.is_revoked = True

    return {"message": "Password reset successfully. Please log in again."}


# ---------------------------------------------------------------------------
# MFA Setup
# ---------------------------------------------------------------------------
@router.post("/mfa/setup", response_model=EnableMFAResponse)
async def setup_mfa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EnableMFAResponse:
    """UC-04: Generate TOTP secret and QR code for MFA setup."""
    if current_user.mfa_enabled or current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is already enabled or setup is already pending.")
    secret = generate_totp_secret()
    totp_uri = get_totp_uri(secret, current_user.email)
    qr_b64 = generate_qr_code_base64(totp_uri)
    # Temporarily store secret — confirmed in /mfa/confirm
    current_user.mfa_secret = secret
    await db.flush()
    return EnableMFAResponse(secret=secret, qr_code_base64=qr_b64, totp_uri=totp_uri)


@router.post("/mfa/confirm", response_model=BackupCodesResponse)
async def confirm_mfa(
    body: ConfirmMFARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BackupCodesResponse:
    """UC-04: Confirm TOTP code and activate MFA; return backup codes."""
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA setup not initiated.")
    if not verify_totp(current_user.mfa_secret, body.totp_code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")

    codes = generate_backup_codes()
    current_user.mfa_enabled = True
    current_user.mfa_backup_codes = hash_backup_codes(codes)
    return BackupCodesResponse(backup_codes=codes)


@router.delete("/mfa/disable")
async def disable_mfa(
    body: ConfirmMFARequest,
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Disable MFA after confirming current TOTP."""
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")
    if not verify_totp(current_user.mfa_secret, body.totp_code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    return {"message": "MFA disabled."}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
@router.post("/logout")
async def logout(
    body: RefreshRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    """Revoke refresh token and blacklist current access JWT."""
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.is_revoked = True
    return {"message": "Logged out successfully."}


# ---------------------------------------------------------------------------
# Change Password (authenticated — UC-10)
# ---------------------------------------------------------------------------
@router.post("/change-password")
async def change_password(
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change password while authenticated. Requires current password."""
    from pydantic import BaseModel

    current_pw = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    if not verify_password(current_pw, current_user.hashed_password or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password.")

    if len(new_pw) < 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be at least 12 characters.")

    current_user.hashed_password = hash_password(new_pw)
    current_user.last_password_change = datetime.now(timezone.utc)
    return {"message": "Password changed successfully."}


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------
@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    """List all active (non-revoked, non-expired) refresh tokens for the user."""
    from sqlalchemy import and_

    result = await db.execute(
        select(RefreshToken).where(
            and_(
                RefreshToken.user_id == current_user.id,
                RefreshToken.is_revoked.is_(False),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
    )
    sessions = result.scalars().all()

    def _parse_ua(ua: str | None) -> str:
        """Convert raw User-Agent string to human-readable device label."""
        if not ua:
            return "Unknown device"
        s = ua.lower()
        # OS
        if "windows" in s:
            os_ = "Windows"
        elif "mac os" in s or "macintosh" in s:
            os_ = "macOS"
        elif "iphone" in s or "ipad" in s:
            os_ = "iOS"
        elif "android" in s:
            os_ = "Android"
        elif "linux" in s:
            os_ = "Linux"
        else:
            os_ = None
        # Browser
        if "edg/" in s or "edge/" in s:
            browser = "Edge"
        elif "chrome" in s and "chromium" not in s:
            browser = "Chrome"
        elif "firefox" in s:
            browser = "Firefox"
        elif "safari" in s and "chrome" not in s:
            browser = "Safari"
        elif "opera" in s or "opr/" in s:
            browser = "Opera"
        else:
            browser = None
        if browser and os_:
            return f"{browser} on {os_}"
        if browser:
            return browser
        if os_:
            return f"{os_} device"
        return "Unknown device"

    return [
        {
            "id": str(s.id),
            "device_info": _parse_ua(s.device_info),
            "ip_address": None,  # Omit raw internal IPs from response
            "expires_at": s.expires_at.isoformat(),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]


@router.delete("/sessions/{token_id}")
async def revoke_session(
    token_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a specific refresh token (remote session logout)."""
    token = await db.get(RefreshToken, token_id)
    if not token or token.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    token.is_revoked = True
    return {"message": "Session revoked."}
