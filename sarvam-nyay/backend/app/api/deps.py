"""
VeriDictum AI — FastAPI Dependency Injection
Authentication guards, permission checks, rate limiters.
"""

from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AccountStatus, Case, CaseMember, CasePermission, User, UserRole
from app.utils.security import decode_token

security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Redis client — optional, degrades gracefully when Redis is unavailable
# ---------------------------------------------------------------------------
_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
            await client.ping()
            _redis_client = client
        except Exception:
            return None
    return _redis_client


# ---------------------------------------------------------------------------
# Current user extraction
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> User:
    """Validate JWT and return the authenticated User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Check token blacklist in Redis (skip if Redis unavailable)
    if redis is not None:
        try:
            jti = payload.get("jti", "")
            if jti and await redis.get(f"blacklist:jti:{jti}"):
                raise credentials_exception
        except Exception:
            pass  # Redis unavailable — allow token

    # Load user from DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    # Block locked/suspended/deactivated accounts
    if user.status in (AccountStatus.SUSPENDED, AccountStatus.LOCKED, AccountStatus.DEACTIVATED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value.lower()}.",
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


# ---------------------------------------------------------------------------
# Role-based guards
# ---------------------------------------------------------------------------
def require_roles(*roles: UserRole):
    """Factory: returns a dependency that enforces the given roles."""
    async def _check(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user
    return _check


require_admin = require_roles(UserRole.ADMIN)
require_attorney_or_above = require_roles(UserRole.ADMIN, UserRole.ATTORNEY)
require_paralegal_or_above = require_roles(UserRole.ADMIN, UserRole.ATTORNEY, UserRole.PARALEGAL)


# ---------------------------------------------------------------------------
# Case permission guards
# ---------------------------------------------------------------------------
async def get_case_with_permission(
    case_id: UUID,
    required_permission: CasePermission,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Case:
    """Load case and verify current user has sufficient permission."""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    if case.organisation_id != current_user.organisation_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # ADMIN can access everything in their org
    if current_user.role == UserRole.ADMIN:
        return case

    # Check case membership
    member_result = await db.execute(
        select(CaseMember).where(
            CaseMember.case_id == case_id,
            CaseMember.user_id == current_user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this case.")

    permission_order = {
        CasePermission.VIEWER: 0,
        CasePermission.EDITOR: 1,
        CasePermission.CASE_OWNER: 2,
    }
    if permission_order[member.permission] < permission_order[required_permission]:
        raise HTTPException(status_code=403, detail="Insufficient case permission.")

    return case


# ---------------------------------------------------------------------------
# Rate limiting (gracefully disabled when Redis is unavailable)
# ---------------------------------------------------------------------------
async def rate_limit(request: Request, redis=Depends(get_redis)) -> None:
    """Simple sliding-window rate limiter per IP. No-ops when Redis is down."""
    if redis is None:
        return
    try:
        ip = request.client.host if request.client else "unknown"
        key = f"rate:{ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > settings.RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Redis unavailable — skip rate limiting
