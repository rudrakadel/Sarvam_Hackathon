"""
VeriDictum AI — Document Upload & OCR API
Handles FR-16 to FR-20 (document OCR, confidence display, corrections).
"""

import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import _require_case_permission
from app.config import settings
from app.models import CasePermission, Document, DocumentPage, ProcessingStatus, User
from app.schemas.case import DocumentResponse
from app.utils.storage import (
    build_document_blob_name,
    compute_sha256,
    detect_mime_type,
    upload_blob,
)

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["Documents & OCR"])

ALLOWED_DOC_FORMATS = {"pdf", "docx", "tif", "tiff", "png", "jpg", "jpeg"}


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    case_id: UUID,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """UC-26: Upload a legal document for OCR processing."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_DOC_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'.")

    data = await file.read()
    if len(data) > settings.MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 500 MB limit.")

    sha256 = compute_sha256(data)

    # Duplicate detection within case
    existing = await db.execute(
        select(Document).where(Document.case_id == case_id, Document.sha256_hash == sha256)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A file with this content already exists in the case.")

    doc_id = uuid.uuid4()
    blob_name = build_document_blob_name(case_id, doc_id, file.filename)
    mime = detect_mime_type(file.filename)

    try:
        blob_path = upload_blob(
            settings.AZURE_STORAGE_CONTAINER_DOCUMENTS,
            blob_name,
            data,
            content_type=mime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    doc = Document(
        id=doc_id,
        case_id=case_id,
        uploaded_by_id=current_user.id,
        original_filename=file.filename,
        blob_path=blob_path,
        file_size_bytes=len(data),
        format=ext,
        sha256_hash=sha256,
        mime_type=mime,
        document_type=document_type,
        author=author,
        status=ProcessingStatus.QUEUED,
    )
    db.add(doc)
    await db.flush()

    # Enqueue OCR task (non-blocking — skip if broker unavailable)
    try:
        from app.tasks.ocr import process_document_ocr
        task = process_document_ocr.delay(str(doc.id))
        doc.celery_task_id = task.id
    except Exception:
        pass  # Celery unavailable in dev

    return DocumentResponse.model_validate(doc)


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    case_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[DocumentResponse]:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(select(Document).where(Document.case_id == case_id).offset(skip).limit(limit))
    return [DocumentResponse.model_validate(d) for d in result.scalars()]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    case_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.case_id == case_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/pages")
async def get_pages(
    case_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """UC-27: View OCR extracted text with confidence scores per page."""
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    pages = result.scalars().all()
    return [
        {
            "page_number": p.page_number,
            "extracted_text": p.corrected_text if p.is_corrected else p.extracted_text,
            "confidence": p.confidence,
            "has_handwriting": p.has_handwriting,
            "is_corrected": p.is_corrected,
        }
        for p in pages
    ]


@router.patch("/{document_id}/pages/{page_number}/correct")
async def correct_page_text(
    case_id: UUID,
    document_id: UUID,
    page_number: int,
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-27: Correct low-confidence OCR text inline."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    result = await db.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")

    page.corrected_text = body.get("text", "")
    page.is_corrected = True
    page.corrected_by_id = current_user.id

    # Also update parent document extracted_text
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_result.scalar_one_or_none()
    if doc:
        pages_result = await db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        all_pages = pages_result.scalars().all()
        doc.extracted_text = "\n\n".join(
            p.corrected_text or p.extracted_text or "" for p in all_pages
        )

    return {"message": "Page text corrected."}


@router.delete("/{document_id}")
async def delete_document(
    case_id: UUID,
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _require_case_permission(db, case_id, current_user, CasePermission.CASE_OWNER)
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.case_id == case_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    await db.delete(doc)
    return Response(status_code=204)
