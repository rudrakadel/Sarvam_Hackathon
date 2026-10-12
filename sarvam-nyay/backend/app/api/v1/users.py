"""
VeriDictum AI — User Management API (UC-05, UC-07, UC-10)
Invite users, manage roles, suspend/deactivate accounts.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_admin, require_paralegal_or_above
from app.models.user import AccountStatus, Invitation, User, UserRole
from app.schemas.user import InvitationResponse, InviteUserRequest, UpdateRoleRequest, UserResponse, UserUpdate
from app.utils.email import send_invitation_email
from app.utils.security import generate_secure_token

router = APIRouter(prefix="/users", tags=["users"])


# ─── List Organisation Users ─────────────────────────────────────────────────


@router.get("", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_paralegal_or_above),
):
    """Return all active users in the caller's organisation."""
    result = await db.execute(
        select(User)
        .where(
            and_(
                User.organisation_id == current_user.organisation_id,
                User.status != AccountStatus.DEACTIVATED,
            )
        )
        .order_by(User.full_name)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# ─── Get Single User ──────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    """Return the authenticated user's own profile."""
    return current_user


@router.get("/invitations/pending", response_model=list[InvitationResponse])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all pending invitations for the organisation."""
    result = await db.execute(
        select(Invitation).where(
            Invitation.organisation_id == current_user.organisation_id,
            Invitation.status == "PENDING",
            Invitation.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_paralegal_or_above),
):
    """Retrieve a single user by ID (same organisation only)."""
    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ─── Invite User (UC-05) ──────────────────────────────────────────────────────


@router.post("/invite", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: InviteUserRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Send an email invitation to a new user. Only admins can invite."""
    existing = await db.execute(
        select(User).where(
            User.email == payload.email.lower(),
            User.organisation_id == current_user.organisation_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in your organisation",
        )

    raw_token = generate_secure_token(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invitation = Invitation(
        organisation_id=current_user.organisation_id,
        invited_by_id=current_user.id,
        invitee_email=payload.email.lower(),
        role=payload.role,
        token=raw_token,
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.flush()
    await db.commit()

    background_tasks.add_task(
        send_invitation_email,
        payload.email,
        current_user.full_name,
        "VeriDictum AI",
        payload.role.value,
        raw_token,
    )

    return invitation


# ─── Update User Role (UC-07) ─────────────────────────────────────────────────


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: UUID,
    payload: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a user's role. Admins cannot modify their own role."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot modify your own role",
        )

    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.role = payload.role
    return user


# ─── Update User Profile (UC-10) ─────────────────────────────────────────────


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update user profile fields. Users may update themselves; admins any org user."""
    # current_user.id is stored as a string via UUIDString; the path param
    # user_id is parsed as a uuid.UUID object. Compare both as strings so
    # the equality check actually works.
    is_self = str(user_id) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN

    if not is_self and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    return user


# ─── Suspend / Activate User ─────────────────────────────────────────────────


@router.patch("/{user_id}/suspend", response_model=UserResponse)
async def suspend_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Suspend a user account. Admin only."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend yourself",
        )
    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.status = AccountStatus.SUSPENDED
    return user


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reactivate a suspended user account. Admin only."""
    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.status = AccountStatus.ACTIVE
    user.failed_login_attempts = 0
    user.lockout_until = None
    return user


# ─── Soft-Delete User ─────────────────────────────────────────────────────────


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    """Soft-delete a user (GDPR erasure). Admin only. Cannot delete self."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )

    user = await db.get(User, user_id)
    if not user or user.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.status = AccountStatus.DEACTIVATED
    user.email = f"deleted_{user.id}@deleted.invalid"
    user.full_name = "[Deleted User]"
    user.mfa_secret = None
    user.mfa_backup_codes = None
    return Response(status_code=204)


# ─── Revoke Invitation ────────────────────────────────────────────────────────


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    """Revoke (delete) a pending invitation."""
    invitation = await db.get(Invitation, invitation_id)
    if not invitation or invitation.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    await db.delete(invitation)
    return Response(status_code=204)
