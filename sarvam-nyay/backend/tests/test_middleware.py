"""
Cross-cutting middleware: body-size limit + security headers.

(Idempotency-Key middleware requires Redis; not exercised here.)
"""

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_security_headers_are_present(client: AsyncClient):
    r = await client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-xss-protection") == "1; mode=block"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    # X-Request-ID is auto-generated when the client doesn't supply one.
    assert r.headers.get("x-request-id")
    assert r.headers.get("x-process-time")
    # Permissions-Policy denies the browser features we don't use.
    permissions = r.headers.get("permissions-policy", "")
    assert "camera=()" in permissions
    assert "microphone=()" in permissions


@pytest.mark.asyncio
async def test_request_id_is_echoed_when_client_supplies_it(client: AsyncClient):
    r = await client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers.get("x-request-id") == "trace-abc-123"


@pytest.mark.asyncio
async def test_body_size_limit_rejects_oversized_json(client: AsyncClient):
    """
    Sending a Content-Length above MAX_JSON_BODY_BYTES must be rejected with
    413 before Pydantic / the route handler runs. We craft the request
    manually with a Content-Length header an order of magnitude above the
    cap; the actual body length is moot because the middleware short-circuits
    on the header.
    """
    cap = settings.MAX_JSON_BODY_BYTES
    big = "x" * 32  # body itself stays small — middleware reads the header
    r = await client.post(
        "/api/v1/auth/login",
        content=big,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(cap * 10),
        },
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "Request body too large."
    assert r.json()["limit_bytes"] == cap


@pytest.mark.asyncio
async def test_body_size_limit_allows_normal_payload(client: AsyncClient):
    """A normal small JSON body must pass the middleware — auth will then
    reject it as 401 / 400, but it must not 413."""
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert r.status_code != 413


@pytest.mark.asyncio
async def test_body_size_limit_invalid_content_length_returns_400(client: AsyncClient):
    """A malformed Content-Length header is a client error, not a server crash."""
    r = await client.post(
        "/api/v1/auth/login",
        content="{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "not-a-number",
        },
    )
    assert r.status_code == 400
    assert "Invalid Content-Length" in r.json()["detail"]
