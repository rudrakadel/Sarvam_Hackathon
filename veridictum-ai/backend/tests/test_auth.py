"""
VeriDictum AI — Auth Endpoint Tests
Covers UC-01, UC-02, UC-04, UC-06.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db: AsyncSession):
    """UC-01: Successful registration creates user."""
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Jane Smith",
        "email": "jane@smithlaw.com",
        "password": "SecurePass123!",
        "organisation_name": "Smith & Associates",
    })
    assert response.status_code == 201
    data = response.json()
    assert "user_id" in data
    assert "Registration successful" in data["message"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user):
    """Registering with existing email returns 409."""
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Duplicate User",
        "email": "attorney@testfirm.com",
        "password": "SecurePass123!",
        "organisation_name": "Another Firm",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Short password returns 422."""
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Weak Pass",
        "email": "weak@firm.com",
        "password": "short",
        "firm_name": "Firm",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """UC-02: Valid credentials return JWT tokens."""
    response = await client.post("/api/v1/auth/login", json={
        "email": "attorney@testfirm.com",
        "password": "SecurePass123!",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    """Wrong password returns 401."""
    response = await client.post("/api/v1/auth/login", json={
        "email": "attorney@testfirm.com",
        "password": "WrongPassword123!",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_generic_response(client: AsyncClient):
    """Forgot password always returns generic message (prevents email enumeration)."""
    response = await client.post("/api/v1/auth/forgot-password", json={
        "email": "nonexistent@firm.com",
    })
    assert response.status_code == 200
    assert "reset link" in response.json()["message"]


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """Accessing protected endpoint without JWT returns 401 or 403."""
    response = await client.get("/api/v1/cases")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_protected_endpoint_with_token(client: AsyncClient, auth_headers: dict):
    """Accessing protected endpoint with JWT returns 200."""
    response = await client.get("/api/v1/cases", headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint returns healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
