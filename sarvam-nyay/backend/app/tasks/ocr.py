"""
VeriDictum AI — Document OCR Celery Task
Azure Document Intelligence extraction with per-page confidence scores.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, DocumentPage, ProcessingStatus
from app.tasks.celery_app import celery_app
from app.websocket.pubsub import publish_case_event_sync

logger = logging.getLogger(__name__)

SARVAM_VISION_URL = "https://api.sarvam.ai/doc-ai/v1/job/digitise"


def _get_db_session() -> Session:
    engine = create_engine(settings.SYNC_DATABASE_URL)
    return Session(engine)


def _parse_sarvam_vision_result(result: dict) -> List[Dict[str, Any]]:
    """Parse Sarvam Vision output into page dictionaries with bounding boxes."""
    pages_data = []
    raw_pages = result.get("pages", [])
    if not raw_pages and "text" in result:
        raw_pages = [{"page_number": 1, "text": result.get("text", ""), "blocks": []}]

    for idx, p in enumerate(raw_pages):
        page_num = p.get("page_number", p.get("page_no", idx + 1))
        page_text = p.get("text", "")
        blocks = p.get("blocks", p.get("lines", []))
        bounding_boxes = []
        confidence_sum = 0.0
        has_handwriting = bool(p.get("has_handwriting", False))

        if not page_text and blocks:
            page_text = "\n".join(b.get("text", "") for b in blocks if b.get("text"))

        for b in blocks:
            b_text = b.get("text", "")
            if not b_text:
                continue
            conf = float(b.get("confidence", 0.95))
            confidence_sum += conf
            if b.get("layout_tag") == "handwriting" or b.get("is_handwritten"):
                has_handwriting = True

            poly = b.get("polygon") or b.get("bounding_box") or b.get("bbox")
            if poly:
                if isinstance(poly, list) and len(poly) == 4 and isinstance(poly[0], (int, float)):
                    ymin, xmin, ymax, xmax = poly
                    normalized_poly = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
                else:
                    normalized_poly = poly
                bounding_boxes.append({
                    "text": b_text,
                    "confidence": conf,
                    "polygon": normalized_poly,
                })

        avg_conf = (confidence_sum / len(blocks)) if blocks else 0.95
        pages_data.append({
            "page_number": page_num,
            "extracted_text": page_text,
            "confidence": avg_conf,
            "has_handwriting": has_handwriting,
            "bounding_boxes": bounding_boxes[:500],
        })

    return pages_data


def _process_with_sarvam_vision(doc_filename: str, doc_data: bytes, mime_type: str) -> List[Dict[str, Any]]:
    """Submit document to Sarvam Vision API."""
    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
    files = {"file": (doc_filename, doc_data, mime_type or "application/pdf")}
    data = {
        "output_format": "json",
        "model": settings.SARVAM_VISION_MODEL,
        "language": settings.SARVAM_LANGUAGE_CODE,
    }
    response = httpx.post(
        SARVAM_VISION_URL,
        headers=headers,
        files=files,
        data=data,
        timeout=300.0,
    )
    response.raise_for_status()
    return _parse_sarvam_vision_result(response.json())


def _process_with_local_pdf(doc_data: bytes) -> List[Dict[str, Any]]:
    """Local fallback parser using PyMuPDF or plain text extraction."""
    try:
        import fitz
        doc = fitz.open(stream=doc_data, filetype="pdf")
        pages = []
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text()
            words = page.get_text("words")
            bboxes = [
                {
                    "text": w[4],
                    "confidence": 1.0,
                    "polygon": [[w[0], w[1]], [w[2], w[1]], [w[2], w[3]], [w[0], w[3]]],
                }
                for w in words[:500]
            ]
            pages.append({
                "page_number": i + 1,
                "extracted_text": text,
                "confidence": 1.0,
                "has_handwriting": False,
                "bounding_boxes": bboxes,
            })
        return pages
    except Exception:
        text = doc_data.decode("utf-8", errors="ignore")[:10000]
        return [{
            "page_number": 1,
            "extracted_text": text,
            "confidence": 0.9,
            "has_handwriting": False,
            "bounding_boxes": [],
        }]


@celery_app.task(
    name="app.tasks.ocr.process_document_ocr",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,    # cap at 5 min — OCR is faster than transcription
    retry_jitter=True,
    max_retries=4,
    acks_late=True,
)
def process_document_ocr(self, document_id: str) -> dict:
    """
    OCR pipeline:
    1. Download document from Local Storage
    2. Analyse with Sarvam Vision (or Local PDF parser fallback)
    3. Persist DocumentPage records with bounding boxes
    4. Publish case completion event
    """
    with _get_db_session() as db:
        try:
            doc = db.get(Document, document_id)
            if not doc:
                return {"status": "error", "message": "Document not found"}

            doc.status = ProcessingStatus.PROCESSING
            db.commit()

            # --- Download from local storage ---
            from app.utils.storage import download_blob
            doc_data = download_blob(doc.blob_path)

            # --- Extract text and bounding boxes based on provider ---
            if settings.OCR_PROVIDER == "sarvam" and settings.SARVAM_API_KEY:
                try:
                    pages_data = _process_with_sarvam_vision(
                        doc.original_filename, doc_data, doc.mime_type or "application/pdf"
                    )
                except Exception as exc:
                    logger.warning(f"Sarvam Vision failed ({exc}), falling back to local PDF parser")
                    pages_data = _process_with_local_pdf(doc_data)
            else:
                pages_data = _process_with_local_pdf(doc_data)

            # --- Process and persist pages ---
            full_text_parts = []
            total_confidence = 0.0
            has_handwriting = False

            for p in pages_data:
                page_text = p.get("extracted_text", "")
                full_text_parts.append(page_text)
                if p.get("confidence") is not None:
                    total_confidence += p["confidence"]
                if p.get("has_handwriting"):
                    has_handwriting = True

                db_page = DocumentPage(
                    document_id=doc.id,
                    page_number=p.get("page_number", 1),
                    extracted_text=page_text,
                    confidence=p.get("confidence"),
                    has_handwriting=p.get("has_handwriting", False),
                    bounding_boxes=p.get("bounding_boxes", [])[:500],
                )
                db.add(db_page)

            avg_confidence = (total_confidence / len(pages_data)) if pages_data else None
            doc.extracted_text = "\n\n--- PAGE BREAK ---\n\n".join(full_text_parts)
            doc.avg_confidence = avg_confidence
            doc.page_count = len(pages_data)
            doc.has_handwriting = has_handwriting
            doc.status = ProcessingStatus.COMPLETE
            db.commit()

            publish_case_event_sync(str(doc.case_id), "ocr_complete", {
                "document_id": document_id,
                "pages": len(pages_data),
                "status": "COMPLETE",
            })

            logger.info(f"OCR complete for document {document_id}: {len(pages_data)} pages, avg confidence {avg_confidence or 0.0:.2f}")
            return {
                "status": "complete",
                "document_id": document_id,
                "pages": len(pages_data),
                "avg_confidence": avg_confidence,
            }

        except Exception as exc:
            logger.exception(f"OCR failed for document {document_id}: {exc}")
            try:
                doc.status = ProcessingStatus.FAILED
                doc.error_message = str(exc)[:1000]
                db.commit()
            except Exception:
                pass
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
