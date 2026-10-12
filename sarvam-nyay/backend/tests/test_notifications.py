"""VeriDictum AI — Notifications endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.notification import Notification, NotificationType


async def _seed_notification(db: AsyncSession, user: User, *, is_read: bool = False) -> Notification:
    n = Notification(
        user_id=user.id,
        type=NotificationType.SYSTEM,
        title="Test notification",
        body="This is a test.",
        is_read=is_read,
    )
    db.add(n)
    await db.flush()
    return n


@pytest.mark.asyncio
async def test_list_notifications_empty(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["unread_count"] == 0


@pytest.mark.asyncio
async def test_list_notifications_returns_seeded(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    await _seed_notification(db, test_user)
    await _seed_notification(db, test_user, is_read=True)

    r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["unread_count"] == 1


@pytest.mark.asyncio
async def test_unread_only_filter(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    await _seed_notification(db, test_user)
    await _seed_notification(db, test_user, is_read=True)

    r = await client.get("/api/v1/notifications?unread_only=true", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert all(not item["is_read"] for item in data["items"])


@pytest.mark.asyncio
async def test_mark_read(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    n = await _seed_notification(db, test_user)
    assert not n.is_read

    r = await client.patch(f"/api/v1/notifications/{n.id}/read", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_read"] is True


@pytest.mark.asyncio
async def test_mark_all_read(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    for _ in range(3):
        await _seed_notification(db, test_user)

    r = await client.patch("/api/v1/notifications/read-all", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["marked_read"] == 3

    count_r = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert count_r.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_delete_notification(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    n = await _seed_notification(db, test_user)

    r = await client.delete(f"/api/v1/notifications/{n.id}", headers=auth_headers)
    assert r.status_code == 204

    list_r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert list_r.json()["total"] == 0


@pytest.mark.asyncio
async def test_notification_not_found(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.patch(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000/read",
        headers=auth_headers,
    )
    assert r.status_code == 404
