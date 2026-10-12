"""
VeriDictum AI — User & Organisation Pydantic Schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.user import AccountStatus, SubscriptionTier, UserRole


# --- Organisation ---
class OrganisationBase(BaseModel):
    name: str
    domain: Optional[str] = None
    subscription_tier: SubscriptionTier = SubscriptionTier.STARTER


class OrganisationCreate(OrganisationBase):
    pass


class OrganisationResponse(OrganisationBase):
    id: UUID
    is_active: bool
    sso_enabled: bool
    storage_quota_bytes: int
    storage_used_bytes: int
    max_cases: int
    max_users: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- User ---
class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    role: UserRole = UserRole.ATTORNEY


class UserCreate(UserBase):
    password: str
    organisation_id: UUID


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    timezone: Optional[str] = None
    avatar_url: Optional[str] = None
    notification_preferences: Optional[dict] = None


class UserResponse(UserBase):
    id: UUID
    organisation_id: UUID
    status: AccountStatus
    email_verified: bool
    mfa_enabled: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    """Safe user info for sharing within organisation (no sensitive fields)."""
    id: UUID
    full_name: str
    email: str
    role: UserRole

    model_config = {"from_attributes": True}


# --- Invitations ---
class InviteUserRequest(BaseModel):
    email: EmailStr
    role: UserRole


class InvitationResponse(BaseModel):
    id: UUID
    invitee_email: str
    role: UserRole
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Role update ---
class UpdateRoleRequest(BaseModel):
    role: UserRole


# --- Active sessions ---
class SessionResponse(BaseModel):
    id: UUID
    device_info: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    expires_at: datetime
    is_current: bool

    model_config = {"from_attributes": True}
