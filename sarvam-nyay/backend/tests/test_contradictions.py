"""VeriDictum AI — Contradictions API tests (FR-21 through FR-25)."""

import uuid as _uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisJob,
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    User,
)


async def _create_case(client: AsyncClient, headers: dict, suffix: str = "001") -> str:
    r = await client.post(
        "/api/v1/cases",
        json={"case_number": f"CONT-{suffix}", "title": f"Test Case {suffix}", "case_type": "CRIMINAL"},
        headers=headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_contradiction(db: AsyncSession, case_id: str, user: User) -> Contradiction:
    c = Contradiction(
        case_id=_uuid.UUID(case_id),
        transcript_text="The defendant said he was at home on the 15th.",
        document_text="Exhibit A shows defendant at the warehouse on the 15th.",
        severity=ContradictionSeverity.HIGH,
        confidence_score=0.91,
        explanation="Location discrepancy between testimony and documentary evidence.",
        contradiction_type="factual",
        status=ContradictionStatus.AI_SUGGESTED,
    )
    db.add(c)
    await db.flush()
    return c


@pytest.mark.asyncio
async def test_list_contradictions_empty(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "LIST-EMPTY")
    r = await client.get(f"/api/v1/cases/{case_id}/contradictions", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_contradiction_stats_empty(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "STATS-EMPTY")
    r = await client.get(
        f"/api/v1/cases/{case_id}/contradictions/summary/stats",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_contradictions_with_data(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    case_id = await _create_case(client, auth_headers, "WITH-DATA")
    await _seed_contradiction(db, case_id, test_user)

    r = await client.get(f"/api/v1/cases/{case_id}/contradictions", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    c = data["items"][0]
    assert c["severity"] == "HIGH"
    assert c["status"] == "AI_SUGGESTED"
    assert c["confidence_score"] == pytest.approx(0.91, abs=0.01)


@pytest.mark.asyncio
async def test_review_contradiction_confirm(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    case_id = await _create_case(client, auth_headers, "REVIEW-CONF")
    c = await _seed_contradiction(db, case_id, test_user)

    r = await client.patch(
        f"/api/v1/cases/{case_id}/contradictions/{c.id}/review",
        json={"status": "CONFIRMED", "attorney_notes": "Verified against exhibit A."},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "CONFIRMED"
    assert data["attorney_notes"] == "Verified against exhibit A."


@pytest.mark.asyncio
async def test_review_contradiction_reject(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    case_id = await _create_case(client, auth_headers, "REVIEW-REJ")
    c = await _seed_contradiction(db, case_id, test_user)

    r = await client.patch(
        f"/api/v1/cases/{case_id}/contradictions/{c.id}/review",
        json={"status": "REJECTED", "attorney_notes": "Different day referenced."},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_trigger_analysis_queues_job(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "TRIGGER")
    r = await client.post(
        f"/api/v1/cases/{case_id}/contradictions/analyze",
        headers=auth_headers,
    )
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert "Analysis queued" in data["message"]


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient, auth_headers: dict) -> None:
    case_id = await _create_case(client, auth_headers, "JOBS")
    # Trigger a job first
    await client.post(
        f"/api/v1/cases/{case_id}/contradictions/analyze",
        headers=auth_headers,
    )
    r = await client.get(
        f"/api/v1/cases/{case_id}/contradictions/jobs",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_contradiction_severity_filter(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
) -> None:
    case_id = await _create_case(client, auth_headers, "SEV-FILTER")
    high = await _seed_contradiction(db, case_id, test_user)
    # Add a LOW severity one
    low = Contradiction(
        case_id=_uuid.UUID(case_id),
        transcript_text="Minor discrepancy in date.",
        document_text="Document says slightly different date.",
        severity=ContradictionSeverity.LOW,
        confidence_score=0.60,
        explanation="Low severity discrepancy.",
        status=ContradictionStatus.AI_SUGGESTED,
    )
    db.add(low)
    await db.flush()

    r = await client.get(
        f"/api/v1/cases/{case_id}/contradictions?severity=HIGH",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["severity"] == "HIGH" for i in items)
