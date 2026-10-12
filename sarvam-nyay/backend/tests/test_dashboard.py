"""VeriDictum AI — Dashboard endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_unauthenticated(client: AsyncClient) -> None:
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_returns_expected_shape(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()

    assert "cases" in data
    assert "contradictions" in data
    assert "evidence" in data
    assert "reports" in data
    assert "recent_analysis_jobs" in data

    assert isinstance(data["cases"]["total"], int)
    assert isinstance(data["contradictions"]["total"], int)
    assert isinstance(data["evidence"]["total_audio"], int)
    assert isinstance(data["evidence"]["total_documents"], int)
    assert isinstance(data["recent_analysis_jobs"], list)


@pytest.mark.asyncio
async def test_dashboard_counts_after_case_created(client: AsyncClient, auth_headers: dict) -> None:
    # Initially zero cases
    r_before = await client.get("/api/v1/dashboard", headers=auth_headers)
    before = r_before.json()["cases"]["total"]

    # Create a case
    await client.post(
        "/api/v1/cases",
        json={"case_number": "DASH-001", "title": "Dashboard test case", "case_type": "CIVIL"},
        headers=auth_headers,
    )

    r_after = await client.get("/api/v1/dashboard", headers=auth_headers)
    after = r_after.json()["cases"]["total"]

    assert after == before + 1


@pytest.mark.asyncio
async def test_dashboard_open_case_count(client: AsyncClient, auth_headers: dict) -> None:
    await client.post(
        "/api/v1/cases",
        json={"case_number": "OPEN-001", "title": "Open case", "case_type": "CRIMINAL"},
        headers=auth_headers,
    )
    r = await client.get("/api/v1/dashboard", headers=auth_headers)
    data = r.json()
    assert data["cases"]["open"] >= 1
