"""
User-admin router coverage.

Exercises: list, /me, get-by-id, invite (admin-only), update-profile,
suspend / activate / delete, role escalation gating, cross-org isolation.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountStatus,
    Organisation,
    SubscriptionTier,
    User,
    UserRole,
)
from app.utils.security import create_access_token, hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession, test_org: Organisation) -> User:
    """An ADMIN in the same org as `test_user` — needed for invite/suspend."""
    u = User(
        organisation_id=test_org.id,
        email="admin@testfirm.com",
        hashed_password=hash_password("AdminPass1!"),
        full_name="Org Admin",
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict:
    token = create_access_token(str(admin_user.id), {"role": admin_user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_org_user(db: AsyncSession) -> User:
    """User in a DIFFERENT organisation — used to test tenant isolation."""
    org = Organisation(
        name="Rival Law Firm",
        subscription_tier=SubscriptionTier.STARTER,
    )
    db.add(org)
    await db.flush()
    u = User(
        organisation_id=org.id,
        email="rival@otherfirm.com",
        hashed_password=hash_password("RivalPass1!"),
        full_name="Rival Lawyer",
        role=UserRole.ATTORNEY,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db.add(u)
    await db.flush()
    return u


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_authenticated_user(client: AsyncClient, auth_headers: dict, test_user: User):
    r = await client.get("/api/v1/users/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == test_user.email
    assert body["full_name"] == test_user.full_name
    assert body["role"] == "ATTORNEY"


@pytest.mark.asyncio
async def test_me_rejects_anonymous(client: AsyncClient):
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_users_returns_org_members(
    client: AsyncClient, auth_headers: dict, test_user: User, admin_user: User
):
    r = await client.get("/api/v1/users", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    emails = {u["email"] for u in items}
    assert test_user.email in emails
    assert admin_user.email in emails


@pytest.mark.asyncio
async def test_list_users_does_not_leak_other_orgs(
    client: AsyncClient, auth_headers: dict, other_org_user: User
):
    r = await client.get("/api/v1/users", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    emails = {u["email"] for u in items}
    assert other_org_user.email not in emails


@pytest.mark.asyncio
async def test_get_user_by_id_404s_for_cross_org(
    client: AsyncClient, auth_headers: dict, other_org_user: User
):
    r = await client.get(f"/api/v1/users/{other_org_user.id}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_invite_requires_admin(client: AsyncClient, auth_headers: dict):
    """ATTORNEY token cannot invite — only ADMIN."""
    r = await client.post(
        "/api/v1/users/invite",
        headers=auth_headers,
        json={"email": "new@testfirm.com", "role": "ATTORNEY"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invite_succeeds_as_admin(
    client: AsyncClient, admin_headers: dict
):
    r = await client.post(
        "/api/v1/users/invite",
        headers=admin_headers,
        json={"email": "new@testfirm.com", "role": "ATTORNEY"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["invitee_email"] == "new@testfirm.com"
    assert body["role"] == "ATTORNEY"
    assert body["status"] == "PENDING"


@pytest.mark.asyncio
async def test_invite_rejects_duplicate_email(
    client: AsyncClient, admin_headers: dict, test_user: User
):
    """Inviting an email that already belongs to an org member → 409."""
    r = await client.post(
        "/api/v1/users/invite",
        headers=admin_headers,
        json={"email": test_user.email, "role": "ATTORNEY"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_update_own_profile(client: AsyncClient, auth_headers: dict, test_user: User):
    r = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=auth_headers,
        json={"full_name": "John Updated Attorney"},
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "John Updated Attorney"


@pytest.mark.asyncio
async def test_suspend_requires_admin(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    r = await client.patch(
        f"/api/v1/users/{test_user.id}/suspend", headers=auth_headers
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_suspend_then_activate_round_trip(
    client: AsyncClient, admin_headers: dict, test_user: User
):
    r1 = await client.patch(
        f"/api/v1/users/{test_user.id}/suspend", headers=admin_headers
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "SUSPENDED"

    r2 = await client.patch(
        f"/api/v1/users/{test_user.id}/activate", headers=admin_headers
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "ACTIVE"
