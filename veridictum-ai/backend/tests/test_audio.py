"""
Audio router coverage.

Uploads are I/O-heavy: in the test environment we monkeypatch the Azure
Blob upload to a stub that returns a deterministic blob path. The Celery
enqueue is already wrapped in try/except so it silently no-ops in tests.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AudioFile,
    Case,
    CaseMember,
    CasePermission,
    CaseStatus,
    CaseType,
    ProcessingStatus,
    User,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_case(db: AsyncSession, test_user: User) -> Case:
    """A case owned by test_user. The route uses _require_case_permission
    which checks the case_members table — `created_by_id` alone doesn't
    grant access, so we also insert a CASE_OWNER membership row (matching
    what POST /cases does in production)."""
    case = Case(
        organisation_id=test_user.organisation_id,
        created_by_id=test_user.id,
        case_number="TEST-CR-0001",
        title="Test Case for Audio",
        case_type=CaseType.CRIMINAL,
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
    """Replace the Azure Blob upload with a stub that returns the blob name.

    Patches the *imported* reference inside the router module so the real
    `app.utils.storage.upload_blob` is never reached.
    """
    def fake_upload(container: str, blob_name: str, data: bytes, content_type=None):
        return f"local-test/{container}/{blob_name}"

    monkeypatch.setattr("app.api.v1.audio.upload_blob", fake_upload)
    monkeypatch.setattr("app.api.v1.documents.upload_blob", fake_upload)


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_audio_succeeds(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    """Multipart upload returns 201 with an AudioFile shape."""
    files = {"file": ("test.wav", io.BytesIO(b"fake-wav-bytes"), "audio/wav")}
    r = await client.post(
        f"/api/v1/cases/{test_case.id}/audio",
        headers=auth_headers,
        files=files,
        data={"language_hint": "en", "speaker_count_hint": "2"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["original_filename"] == "test.wav"
    assert body["case_id"] == str(test_case.id)
    # Celery isn't running — status stays QUEUED, which is the contract.
    assert body["status"] == "QUEUED"
    assert body["file_size_bytes"] == len(b"fake-wav-bytes")


@pytest.mark.asyncio
async def test_upload_audio_rejects_unsupported_format(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    files = {"file": ("doc.txt", io.BytesIO(b"plain text"), "text/plain")}
    r = await client.post(
        f"/api/v1/cases/{test_case.id}/audio", headers=auth_headers, files=files
    )
    assert r.status_code == 400
    assert "Unsupported format" in r.json()["detail"]


@pytest.mark.asyncio
async def test_upload_audio_rejects_anonymous(
    client: AsyncClient, test_case: Case
):
    files = {"file": ("test.wav", io.BytesIO(b"x"), "audio/wav")}
    r = await client.post(
        f"/api/v1/cases/{test_case.id}/audio", files=files
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_audio_empty(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    r = await client.get(
        f"/api/v1/cases/{test_case.id}/audio", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_audio_after_upload(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    # Upload first
    files = {"file": ("evidence.wav", io.BytesIO(b"bytes"), "audio/wav")}
    await client.post(
        f"/api/v1/cases/{test_case.id}/audio", headers=auth_headers, files=files
    )
    r = await client.get(
        f"/api/v1/cases/{test_case.id}/audio", headers=auth_headers
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["original_filename"] == "evidence.wav"


@pytest.mark.asyncio
async def test_get_audio_not_found(
    client: AsyncClient, auth_headers: dict, test_case: Case
):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = await client.get(
        f"/api/v1/cases/{test_case.id}/audio/{fake_id}", headers=auth_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_transcripts_for_audio_without_transcripts(
    client: AsyncClient, auth_headers: dict, test_case: Case, db: AsyncSession
):
    """Newly uploaded audio has no Transcript rows yet — empty list, not 404."""
    files = {"file": ("witness.wav", io.BytesIO(b"x"), "audio/wav")}
    upload = await client.post(
        f"/api/v1/cases/{test_case.id}/audio", headers=auth_headers, files=files
    )
    audio_id = upload.json()["id"]
    r = await client.get(
        f"/api/v1/cases/{test_case.id}/audio/{audio_id}/transcripts",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == []
