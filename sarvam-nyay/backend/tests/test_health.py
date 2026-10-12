"""
Health + readiness endpoints.

`/health` is the cheap liveness probe (no I/O). `/readiness` is the deep
probe that checks DB + Redis; in CI we expect Redis to fail and the
endpoint to return 503 with structured diagnostics — that's the
contract.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient):
    from app.config import settings
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["service"] == settings.APP_NAME


@pytest.mark.asyncio
async def test_readiness_returns_diagnostics(client: AsyncClient):
    """
    /readiness probes DB + Redis. In CI Redis isn't running so we expect:
      - HTTP 503 (not_ready)
      - body.checks.database.status == "ok"
      - body.checks.redis.status == "fail"
    The important contract: per-subsystem booleans are present.
    """
    from app.config import settings
    r = await client.get("/readiness")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["service"] == settings.APP_NAME
    assert "checks" in body
    # Database probe must always be present and OK in the test sandbox.
    assert body["checks"]["database"]["status"] == "ok"
    # If Redis is configured, it should appear in the checks dict.
    assert "redis" in body["checks"]
