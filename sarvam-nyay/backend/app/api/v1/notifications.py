"""
VeriDictum AI — Notifications API
CRUD for in-app notifications (unread count, list, mark-read, delete).
"""

import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models import User
from app.models.notification import Notification, NotificationType

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List notifications for the current user, newest first."""
    base_q = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        base_q = base_q.where(Notification.is_read.is_(False))

    count_row = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_row.scalar() or 0

    paginated = await db.execute(
        base_q.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = paginated.scalars().all()

    return {
        "items": [_serialize(n) for n in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
        "unread_count": await _unread_count(db, current_user.id),
    }


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {"unread_count": await _unread_count(db, current_user.id)}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    n = await _get_notification(db, notification_id, current_user.id)
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
    return _serialize(n)


@router.patch("/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    )
    now = datetime.now(timezone.utc)
    count = 0
    for n in rows.scalars():
        n.is_read = True
        n.read_at = now
        count += 1
    return {"marked_read": count}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    n = await _get_notification(db, notification_id, current_user.id)
    await db.delete(n)
    return Response(status_code=204)


# ── Internal helpers ──────────────────────────────────────────────────────────

async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    type: NotificationType,
    title: str,
    body: str | None = None,
    case_id: UUID | None = None,
) -> Notification:
    """Helper used by other API modules to create notifications."""
    n = Notification(
        user_id=user_id,
        case_id=case_id,
        type=type,
        title=title,
        body=body,
    )
    db.add(n)
    await db.flush()
    return n


async def _unread_count(db: AsyncSession, user_id: UUID) -> int:
    row = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
    )
    return row.scalar() or 0


async def _get_notification(db: AsyncSession, notification_id: UUID, user_id: UUID) -> Notification:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return n


def _serialize(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "user_id": str(n.user_id),
        "case_id": str(n.case_id) if n.case_id else None,
        "type": n.type.value if hasattr(n.type, "value") else n.type,
        "title": n.title,
        "body": n.body,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }
