"""VeriDictum AI — Reports & NL Query API tests (FR-26 through FR-30)."""

import pytest
from httpx import AsyncClient


async def _create_case(client: AsyncClient, headers: dict, suffix: str) -> str:
    r = await client.post(
        "/api/v1/cases",
        json={"case_number": f"RPT-{suffix}", "title": f"Report Test {suffix}", "case_type": "CIVIL"},
        headers=headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_create_report(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "CREATE")
    r = await client.post(
        f"/api/v1/cases/{case_id}/reports",
        json={"title": "Full Contradiction Report", "format": "PDF"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Full Contradiction Report"
    assert data["status"] == "QUEUED"
    assert data["format"] == "PDF"


@pytest.mark.asyncio
async def test_list_reports_empty(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "LIST-EMPTY")
    r = await client.get(f"/api/v1/cases/{case_id}/reports", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_reports_after_create(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "LIST-AFTER")
    await client.post(
        f"/api/v1/cases/{case_id}/reports",
        json={"title": "Test Report", "format": "PDF"},
        headers=auth_headers,
    )
    r = await client.get(f"/api/v1/cases/{case_id}/reports", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_report_by_id(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "GET-BY-ID")
    create_r = await client.post(
        f"/api/v1/cases/{case_id}/reports",
        json={"title": "Get By ID", "format": "PDF"},
        headers=auth_headers,
    )
    report_id = create_r.json()["id"]
    r = await client.get(f"/api/v1/cases/{case_id}/reports/{report_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == report_id


@pytest.mark.asyncio
async def test_get_report_not_found(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "NOT-FOUND")
    r = await client.get(
        f"/api/v1/cases/{case_id}/reports/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_nl_query_returns_answer(client: AsyncClient, auth_headers: dict) -> None:
    """FR-28: NL query returns an answer (may be empty when no corpus indexed)."""
    case_id = await _create_case(client, auth_headers, "NL-QUERY")
    r = await client.post(
        f"/api/v1/cases/{case_id}/query",
        json={"query": "What did the defendant say about the contract?"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "query_text" in data
    assert "answer_text" in data
    assert data["query_text"] == "What did the defendant say about the contract?"


@pytest.mark.asyncio
async def test_nl_query_history(client: AsyncClient, auth_headers: dict) -> None:
    """FR-30: Query history is persisted and retrievable."""
    case_id = await _create_case(client, auth_headers, "NL-HIST")
    await client.post(
        f"/api/v1/cases/{case_id}/query",
        json={"query": "Query A"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/cases/{case_id}/query",
        json={"query": "Query B"},
        headers=auth_headers,
    )
    r = await client.get(f"/api/v1/cases/{case_id}/query/history", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
