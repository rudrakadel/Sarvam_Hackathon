"""VeriDictum AI — WebSocket endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ws_job_endpoint_exists(client: AsyncClient) -> None:
    """Verify the WebSocket job endpoint route is registered in the app."""
    from app.main import app
    ws_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/ws/jobs/{job_id}" in ws_paths


@pytest.mark.asyncio
async def test_ws_case_endpoint_exists(client: AsyncClient) -> None:
    """Verify the WebSocket case endpoint route is registered in the app."""
    from app.main import app
    ws_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/ws/cases/{case_id}" in ws_paths


@pytest.mark.asyncio
async def test_ws_user_endpoint_exists(client: AsyncClient) -> None:
    """Verify the WebSocket user notifications endpoint route is registered."""
    from app.main import app
    ws_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/ws/users/{user_id}" in ws_paths


@pytest.mark.asyncio
async def test_pubsub_broadcast_noop(client: AsyncClient) -> None:
    """Verify pub/sub publish silently ignores failures when Redis is unavailable."""
    from app.websocket.pubsub import publish_event_sync
    # Should not raise even when Redis is unavailable in test environment
    publish_event_sync("job", "fake-job-id", {"event": "job_update", "status": "PROCESSING"})


@pytest.mark.asyncio
async def test_ws_manager_broadcast_no_subscribers() -> None:
    """Broadcast to a topic with no subscribers should not raise."""
    from app.websocket.manager import ws_manager
    await ws_manager.broadcast("job", "nonexistent-id", {"event": "test"})
