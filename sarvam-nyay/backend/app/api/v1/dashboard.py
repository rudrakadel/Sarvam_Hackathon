"""
VeriDictum AI — Dashboard Analytics API
Org-wide summary stats consumed by the dashboard page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models import (
    AnalysisJob,
    AudioFile,
    Case,
    CaseStatus,
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    Document,
    ProcessingStatus,
    Report,
    ReportStatus,
    User,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregated org-level stats for the dashboard."""
    org_id = current_user.organisation_id

    # ── Case counts by status ─────────────────────────────────────────────────
    case_rows = await db.execute(
        select(Case.status, func.count(Case.id).label("n"))
        .where(Case.organisation_id == org_id)
        .group_by(Case.status)
    )
    cases_by_status: dict = {row.status: row.n for row in case_rows}
    total_cases = sum(cases_by_status.values())

    # ── Contradiction counts ──────────────────────────────────────────────────
    contradiction_rows = await db.execute(
        select(Contradiction.severity, func.count(Contradiction.id).label("n"))
        .join(Case, Contradiction.case_id == Case.id)
        .where(Case.organisation_id == org_id)
        .group_by(Contradiction.severity)
    )
    contradictions_by_severity = {row.severity: row.n for row in contradiction_rows}
    total_contradictions = sum(contradictions_by_severity.values())

    critical_count = contradictions_by_severity.get(ContradictionSeverity.CRITICAL, 0)

    # ── Audio & document counts ───────────────────────────────────────────────
    audio_count_row = await db.execute(
        select(func.count(AudioFile.id))
        .join(Case, AudioFile.case_id == Case.id)
        .where(Case.organisation_id == org_id)
    )
    total_audio = audio_count_row.scalar() or 0

    doc_count_row = await db.execute(
        select(func.count(Document.id))
        .join(Case, Document.case_id == Case.id)
        .where(Case.organisation_id == org_id)
    )
    total_documents = doc_count_row.scalar() or 0

    # ── Processing queue ──────────────────────────────────────────────────────
    audio_queue_row = await db.execute(
        select(func.count(AudioFile.id))
        .join(Case, AudioFile.case_id == Case.id)
        .where(
            Case.organisation_id == org_id,
            AudioFile.status.in_([ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING]),
        )
    )
    audio_in_queue = audio_queue_row.scalar() or 0

    doc_queue_row = await db.execute(
        select(func.count(Document.id))
        .join(Case, Document.case_id == Case.id)
        .where(
            Case.organisation_id == org_id,
            Document.status.in_([ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING]),
        )
    )
    doc_in_queue = doc_queue_row.scalar() or 0

    # ── Recent analysis jobs ──────────────────────────────────────────────────
    recent_jobs_rows = await db.execute(
        select(AnalysisJob)
        .join(Case, AnalysisJob.case_id == Case.id)
        .where(Case.organisation_id == org_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(5)
    )
    recent_jobs = [
        {
            "id": str(j.id),
            "case_id": str(j.case_id),
            "status": j.status,
            "total_contradictions_found": j.total_contradictions_found,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in recent_jobs_rows.scalars()
    ]

    # ── Reports ───────────────────────────────────────────────────────────────
    report_rows = await db.execute(
        select(Report.status, func.count(Report.id).label("n"))
        .join(Case, Report.case_id == Case.id)
        .where(Case.organisation_id == org_id)
        .group_by(Report.status)
    )
    reports_by_status = {row.status: row.n for row in report_rows}

    # ── Contradiction review stats ────────────────────────────────────────────
    review_rows = await db.execute(
        select(Contradiction.status, func.count(Contradiction.id).label("n"))
        .join(Case, Contradiction.case_id == Case.id)
        .where(Case.organisation_id == org_id)
        .group_by(Contradiction.status)
    )
    contradictions_by_review_status = {row.status: row.n for row in review_rows}

    return {
        "cases": {
            "total": total_cases,
            "by_status": {k.value if hasattr(k, "value") else k: v for k, v in cases_by_status.items()},
            "open": cases_by_status.get(CaseStatus.OPEN, 0),
            "in_review": cases_by_status.get(CaseStatus.IN_REVIEW, 0),
            "archived": cases_by_status.get(CaseStatus.ARCHIVED, 0),
        },
        "contradictions": {
            "total": total_contradictions,
            "critical": critical_count,
            "by_severity": {
                k.value if hasattr(k, "value") else k: v
                for k, v in contradictions_by_severity.items()
            },
            "by_status": {
                k.value if hasattr(k, "value") else k: v
                for k, v in contradictions_by_review_status.items()
            },
            "pending_review": contradictions_by_review_status.get(ContradictionStatus.AI_SUGGESTED, 0),
        },
        "evidence": {
            "total_audio": total_audio,
            "total_documents": total_documents,
            "audio_in_queue": audio_in_queue,
            "documents_in_queue": doc_in_queue,
            "total_in_queue": audio_in_queue + doc_in_queue,
        },
        "reports": {
            "by_status": {
                k.value if hasattr(k, "value") else k: v
                for k, v in reports_by_status.items()
            },
            "total": sum(reports_by_status.values()),
            "complete": reports_by_status.get(ReportStatus.COMPLETE, 0),
        },
        "recent_analysis_jobs": recent_jobs,
    }
