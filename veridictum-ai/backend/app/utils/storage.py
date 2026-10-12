"""
VeriDictum AI — Storage Utilities
Handles upload, signed URL generation, and deletion.
Falls back to local filesystem when Azure is not configured (dev mode).
"""

import hashlib
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Optional
from uuid import UUID

from app.config import settings

# Local storage fallback directory
_LOCAL_STORAGE = Path(__file__).parent.parent.parent / "tmp_storage"


def upload_blob(
    container: str,
    blob_name: str,
    data: bytes | BinaryIO,
    content_type: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Upload to local filesystem storage. Returns relative container/blob_name path."""
    local_path = _LOCAL_STORAGE / container / blob_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    raw = data if isinstance(data, bytes) else data.read()
    local_path.write_bytes(raw)
    return f"{container}/{blob_name}"


def download_blob(blob_path: str) -> bytes:
    """Download data from local storage path."""
    clean_path = str(blob_path).replace("\\", "/").lstrip("/")
    local_path = _LOCAL_STORAGE / clean_path
    if local_path.exists():
        return local_path.read_bytes()

    # Search by filename if exact container path differs
    filename = Path(clean_path).name
    matches = list(_LOCAL_STORAGE.rglob(filename))
    if matches and matches[0].is_file():
        return matches[0].read_bytes()

    return b""


def generate_sas_url(container: str, blob_name: str, expiry_hours: int = 24, permission: str = "r") -> str:
    """Generate accessible URL for local storage asset."""
    clean_name = str(blob_name).replace("\\", "/").lstrip("/")
    return f"/api/v1/storage/{container}/{clean_name}"


def delete_blob(container: str, blob_name: str) -> None:
    """Delete file from local storage."""
    clean_name = str(blob_name).replace("\\", "/").lstrip("/")
    local_path = _LOCAL_STORAGE / container / clean_name
    if local_path.exists():
        local_path.unlink()


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_audio_blob_name(case_id: UUID, audio_id: UUID, filename: str) -> str:
    ext = (filename or "bin").rsplit(".", 1)[-1].lower()
    return f"cases/{case_id}/audio/{audio_id}.{ext}"


def build_document_blob_name(case_id: UUID, doc_id: UUID, filename: str) -> str:
    ext = (filename or "bin").rsplit(".", 1)[-1].lower()
    return f"cases/{case_id}/documents/{doc_id}.{ext}"


def build_report_blob_name(case_id: UUID, report_id: UUID, fmt: str = "pdf") -> str:
    return f"cases/{case_id}/reports/{report_id}.{fmt}"


def detect_mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename or "")
    return mime or "application/octet-stream"
