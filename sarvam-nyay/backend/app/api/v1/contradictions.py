from datetime import timezone
"""
VeriDictum AI — Contradiction Analysis API
Handles FR-21 to FR-25 (contradiction detection, severity, review).
"""

import math
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import _require_case_permission
from app.models import (
    AnalysisJob,
    CasePermission,
    Contradiction,
    ContradictionStatus,
    User,
)
from app.schemas.case import (
    ContradictionResponse,
    ContradictionReviewRequest,
    PaginatedResponse,
)

router = APIRouter(prefix="/cases/{case_id}/contradictions", tags=["Contradiction Analysis"])


@router.post("/analyze", status_code=202)
async def trigger_analysis(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger contradiction analysis for a case corpus."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)

    job = AnalysisJob(
        case_id=case_id,
        triggered_by_id=current_user.id,
        status="QUEUED",
    )
    db.add(job)
    await db.flush()

    task_id = None
    try:
        from app.tasks.contradiction import run_contradiction_analysis
        task = run_contradiction_analysis.delay(str(case_id), str(job.id))
        task_id = task.id
        job.celery_task_id = task_id
    except Exception:
        pass  # Celery unavailable in dev

    return {"message": "Analysis queued.", "job_id": str(job.id), "task_id": task_id}


@router.get("/jobs")
async def list_jobs(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(AnalysisJob).where(AnalysisJob.case_id == case_id).order_by(AnalysisJob.created_at.desc())
    )
    return [
        {
            "id": str(j.id),
            "status": j.status,
            "total_found": j.total_contradictions_found,
            "created_at": j.created_at.isoformat(),
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in result.scalars()
    ]


@router.get("", response_model=PaginatedResponse)
async def list_contradictions(
    case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """List all contradictions for a case with optional filtering."""
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)

    query = select(Contradiction).where(Contradiction.case_id == case_id)
    if severity:
        query = query.where(Contradiction.severity == severity)
    if status_filter:
        query = query.where(Contradiction.status == status_filter)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(Contradiction.confidence_score.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)

    return PaginatedResponse(
        items=[ContradictionResponse.model_validate(c) for c in result.scalars()],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/{contradiction_id}", response_model=ContradictionResponse)
async def get_contradiction(
    case_id: UUID,
    contradiction_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ContradictionResponse:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(Contradiction).where(
            Contradiction.id == contradiction_id,
            Contradiction.case_id == case_id,
        )
    )
    contradiction = result.scalar_one_or_none()
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction not found.")
    return ContradictionResponse.model_validate(contradiction)


@router.patch("/{contradiction_id}/review", response_model=ContradictionResponse)
async def review_contradiction(
    case_id: UUID,
    contradiction_id: UUID,
    body: ContradictionReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ContradictionResponse:
    """UC: Attorney accepts, rejects, or annotates a contradiction (FR-24)."""
    from datetime import datetime, timezone
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)

    valid_statuses = {s.value for s in ContradictionStatus}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {valid_statuses}")

    result = await db.execute(
        select(Contradiction).where(
            Contradiction.id == contradiction_id,
            Contradiction.case_id == case_id,
        )
    )
    contradiction = result.scalar_one_or_none()
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction not found.")

    contradiction.status = ContradictionStatus(body.status)
    contradiction.reviewed_by_id = current_user.id
    contradiction.reviewed_at = datetime.now(timezone.utc)
    if body.attorney_notes:
        contradiction.attorney_notes = body.attorney_notes

    return ContradictionResponse.model_validate(contradiction)


@router.get("/summary/stats")
async def contradiction_stats(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dashboard summary: counts by severity and status."""
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)

    result = await db.execute(
        select(Contradiction.severity, func.count().label("count"))
        .where(Contradiction.case_id == case_id)
        .group_by(Contradiction.severity)
    )
    by_severity = {row.severity: row.count for row in result}

    result2 = await db.execute(
        select(Contradiction.status, func.count().label("count"))
        .where(Contradiction.case_id == case_id)
        .group_by(Contradiction.status)
    )
    by_status = {row.status: row.count for row in result2}

    # Compute avg confidence so the AI Case Summary panel can render a real
    # number instead of "N/A". Skip if there are no contradictions.
    avg_conf_row = await db.execute(
        select(func.avg(Contradiction.confidence_score))
        .where(Contradiction.case_id == case_id)
    )
    avg_confidence = avg_conf_row.scalar()

    total = sum(by_severity.values())
    # `pending_review` is AI_SUGGESTED items not yet confirmed or rejected.
    pending_review = by_status.get(ContradictionStatus.AI_SUGGESTED, 0)

    return {
        "total": total,
        "by_severity": by_severity,
        "by_status": by_status,
        "pending_review": pending_review,
        "avg_confidence": float(avg_confidence) if avg_confidence is not None else None,
    }
