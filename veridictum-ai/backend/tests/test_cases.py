"""
VeriDictum AI — Cases API tests.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_case(client: AsyncClient, auth_headers: dict) -> None:
    payload = {
        "case_number": "2026-CR-001",
        "title": "State v. Test Defendant",
        "case_type": "CRIMINAL",
    }
    r = await client.post("/api/v1/cases", json=payload, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["case_number"] == "2026-CR-001"
    assert data["status"] == "OPEN"


@pytest.mark.asyncio
async def test_list_cases_empty(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get("/api/v1/cases", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_create_case_duplicate_number(
    client: AsyncClient, auth_headers: dict
) -> None:
    payload = {
        "case_number": "2026-CR-DUP",
        "title": "First case",
        "case_type": "CIVIL",
    }
    r1 = await client.post("/api/v1/cases", json=payload, headers=auth_headers)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/cases", json=payload, headers=auth_headers)
    assert r2.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_get_case_not_found(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get(
        "/api/v1/cases/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_archive_case(client: AsyncClient, auth_headers: dict) -> None:
    # Create
    payload = {
        "case_number": "2026-CR-ARCH",
        "title": "Case to archive",
        "case_type": "OTHER",
    }
    create_r = await client.post("/api/v1/cases", json=payload, headers=auth_headers)
    case_id = create_r.json()["id"]

    # Archive
    r = await client.post(f"/api/v1/cases/{case_id}/archive", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ARCHIVED"


@pytest.mark.asyncio
async def test_update_case_title(client: AsyncClient, auth_headers: dict) -> None:
    payload = {
        "case_number": "2026-CR-UPD",
        "title": "Original title",
        "case_type": "CIVIL",
    }
    create_r = await client.post("/api/v1/cases", json=payload, headers=auth_headers)
    case_id = create_r.json()["id"]

    update_r = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"title": "Updated title"},
        headers=auth_headers,
    )
    assert update_r.status_code == 200
    assert update_r.json()["title"] == "Updated title"
