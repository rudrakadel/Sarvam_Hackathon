"""Phase B + C endpoint module for project_01_veridictum (courtroom audit brief)."""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import router
from app.models import (
    AnalysisJob, AudioFile, Case, Contradiction, ContradictionStatus,
    ContradictionSeverity, Document, User,
)
from app.models.evidence import Transcript
from app.services.courtroom_audit_analyzer import CourtroomAuditAnalyzer
from app.services.courtroom_brief_pdf_service import (
    render_courtroom_brief_pdf, safe_pdf_filename,
)


async def _gather_courtroom_audit(case_id: UUID, db: AsyncSession):
    c_q = await db.execute(select(Case).where(Case.id == case_id))
    case = c_q.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    co_q = await db.execute(select(Contradiction).where(Contradiction.case_id == case_id))
    contradictions = co_q.scalars().all()
    contra_dicts: list[dict] = []
    for c in contradictions:
        contra_dicts.append({
            "id": str(c.id),
            "severity": c.severity.value if hasattr(c.severity, "value") else str(c.severity),
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "confidence_score": float(c.confidence_score or 0),
            "transcript_text": c.transcript_text,
            "document_text": c.document_text,
            "explanation": c.explanation,
        })

    a_q = await db.execute(select(AudioFile).where(AudioFile.case_id == case_id))
    audios = a_q.scalars().all()
    audio_dicts = [
        {
            "id": str(a.id),
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "original_filename": a.original_filename,
        }
        for a in audios
    ]

    d_q = await db.execute(select(Document).where(Document.case_id == case_id))
    docs = d_q.scalars().all()
    doc_dicts = [
        {
            "id": str(d.id),
            "ocr_text": bool(getattr(d, "ocr_text", None) or getattr(d, "extracted_text", None)),
            "indexed_at": getattr(d, "indexed_at", None),
        }
        for d in docs
    ]

    j_q = await db.execute(select(AnalysisJob).where(AnalysisJob.case_id == case_id))
    jobs = j_q.scalars().all()
    job_dicts = [
        {
            "id": str(j.id),
            "status": j.status.value if hasattr(j.status, "value") else str(j.status),
        }
        for j in jobs
    ]

    case_dict = {
        "id": str(case.id),
        "title": getattr(case, "title", None) or getattr(case, "name", None),
        "case_number": getattr(case, "case_number", None),
        "status": case.status.value if hasattr(case.status, "value") else str(case.status),
    }

    analyzer = CourtroomAuditAnalyzer()
    result = await analyzer.analyze(case_dict, contra_dicts, audio_dicts, doc_dicts, job_dicts)

    # Build confirmed-critical examples for the PDF.
    confirmed_critical = [
        c for c in contra_dicts
        if (c.get("status") or "").upper() == "CONFIRMED"
        and (c.get("severity") or "").upper() in {"CRITICAL", "HIGH"}
    ]
    confirmed_critical.sort(key=lambda c: -float(c.get("confidence_score") or 0))

    return case_dict, contra_dicts, audio_dicts, doc_dicts, job_dicts, confirmed_critical, result


@router.post("/{case_id}/courtroom-audit")
async def courtroom_audit(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Phase B — case-level audit over voice transcripts + documents + contradictions."""
    case, contras, audios, docs, jobs, _examples, result = await _gather_courtroom_audit(case_id, db)
    return {
        "status": "completed" if (contras or audios or docs) else "no_content",
        "mode": result.get("mode"),
        "case_id": str(case_id),
        "contradictions_checked": len(contras),
        "audio_files_checked": len(audios),
        "documents_checked": len(docs),
        "analysis_jobs_checked": len(jobs),
        "matrix": result.get("matrix", {}),
        "severity_drift": result.get("severity_drift"),
        "evidence_gaps": result.get("evidence_gaps", []),
        "low_confidence_critical": result.get("low_confidence_critical", []),
        "talking_points": result.get("talking_points", []),
    }


@router.get("/{case_id}/voice-records")
async def list_voice_records(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Phase E — return persisted voice transcripts (one entry per Transcript row) for a case."""
    case_q = await db.execute(select(Case).where(Case.id == case_id))
    case = case_q.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Pull all transcripts joined with their AudioFile so we can surface
    # provider/filename context to the UI.
    t_q = await db.execute(
        select(Transcript, AudioFile)
        .join(AudioFile, AudioFile.id == Transcript.audio_file_id)
        .where(Transcript.case_id == case_id)
        .order_by(Transcript.created_at.desc())
    )
    out: List[Dict[str, Any]] = []
    for trans, audio in t_q.all():
        out.append({
            "id": str(trans.id),
            "audio_file_id": str(trans.audio_file_id),
            "voice_transcript": trans.full_text or "",
            "transcript_status": (
                trans.status.value if hasattr(trans.status, "value") else str(trans.status)
            ),
            "provider": "deepinfra-whisper-large-v3",
            "language": audio.language_hint,
            "word_count": trans.word_count,
            "original_filename": audio.original_filename,
            "created_at": trans.created_at.isoformat() if trans.created_at else None,
        })
    return out


@router.get("/{case_id}/courtroom-brief.pdf")
async def courtroom_brief_pdf(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase C — render the courtroom-ready audit brief PDF."""
    case, contras, audios, docs, jobs, examples, result = await _gather_courtroom_audit(case_id, db)
    pdf_bytes = render_courtroom_brief_pdf(
        case=case,
        matrix=result.get("matrix", {}),
        severity_drift=result.get("severity_drift"),
        evidence_gaps=result.get("evidence_gaps", []),
        low_confidence_critical=result.get("low_confidence_critical", []),
        confirmed_critical_examples=examples,
        talking_points=result.get("talking_points", []),
        generated_by=getattr(current_user, "email", None) or str(current_user.id),
    )
    filename = safe_pdf_filename(str(case_id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-VeriDictum-Confirmed": str(result.get("matrix", {}).get("confirmed_critical", 0)),
            "X-VeriDictum-Unreviewed": str(result.get("matrix", {}).get("ai_suggested_unreviewed_critical", 0)),
            "X-VeriDictum-Gaps": str(len(result.get("evidence_gaps", []))),
            "X-VeriDictum-Mode": result.get("mode", "unknown"),
        },
    )
