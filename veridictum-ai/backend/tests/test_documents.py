"""
Documents router coverage — upload, duplicate detection, list, delete.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseMember, CasePermission, CaseStatus, CaseType, User


@pytest_asyncio.fixture
async def test_case(db: AsyncSession, test_user: User) -> Case:
    """See test_audio.py for why we add the CaseMember row explicitly."""
    case = Case(
        organisation_id=test_user.organisation_id,
        created_by_id=test_user.id,
        case_number="TEST-CV-0001",
        title="Test Case for Documents",
        case_type=CaseType.CIVIL,
        status=CaseStatus.OPEN,
    )
    db.add(case)
    await db.flush()
    db.add(CaseMember(
        case_id=case.id,
        user_id=test_user.id,
        permission=CasePermission.CASE_OWNER,
        granted_by_id=test_user.id,
    ))
    await db.flush()
    return case


@pytest.fixture(autouse=True)
def stub_blob_upload(monkeypatch):
    def fake_upload(container: str, blob_name: str, data: bytes, content_type=None):
        return f"local-test/{container}/{blob_name}"

    monkeypatch.setattr("app.api.v1.documents.upload_blob", fake_upload)


@pytest.mark.asyncio
async def test_upload_document_succeeds(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    files = {"file": ("evidence.pdf", io.BytesIO(b"%PDF-1.4 demo"), "application/pdf")}
    r = await client.post(
        f"/api/v1/cases/{test_case.id}/documents",
        headers=auth_headers,
        files=files,
        data={"document_type": "police_report", "author": "LAPD"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["original_filename"] == "evidence.pdf"
    assert body["document_type"] == "police_report"
    assert body["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_upload_document_rejects_unsupported_format(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    files = {"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = await client.post(
        f"/api/v1/cases/{test_case.id}/documents",
        headers=auth_headers,
        files=files,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_document_duplicate_returns_409(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    """Re-uploading bytes with the same SHA-256 hash must 409."""
    payload = b"%PDF-1.4 deterministic content"
    files1 = {"file": ("a.pdf", io.BytesIO(payload), "application/pdf")}
    r1 = await client.post(
        f"/api/v1/cases/{test_case.id}/documents", headers=auth_headers, files=files1
    )
    assert r1.status_code == 201

    files2 = {"file": ("b.pdf", io.BytesIO(payload), "application/pdf")}
    r2 = await client.post(
        f"/api/v1/cases/{test_case.id}/documents", headers=auth_headers, files=files2
    )
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_list_documents(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    r = await client.get(
        f"/api/v1/cases/{test_case.id}/documents", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_document_round_trip(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    """Upload → delete → list returns empty."""
    files = {"file": ("removable.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")}
    up = await client.post(
        f"/api/v1/cases/{test_case.id}/documents",
        headers=auth_headers,
        files=files,
    )
    doc_id = up.json()["id"]

    rm = await client.delete(
        f"/api/v1/cases/{test_case.id}/documents/{doc_id}", headers=auth_headers
    )
    assert rm.status_code in (200, 204)

    listing = await client.get(
        f"/api/v1/cases/{test_case.id}/documents", headers=auth_headers
    )
    assert listing.json() == []
