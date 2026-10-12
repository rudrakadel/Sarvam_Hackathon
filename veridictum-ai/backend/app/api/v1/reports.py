"""
VeriDictum AI — Report Generation API
Handles FR-26, FR-27 (PDF/DOCX contradiction reports).
"""

import math
import uuid
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import _require_case_permission
from app.models import CasePermission, Report, ReportStatus, User
from app.schemas.case import PaginatedResponse, ReportCreateRequest, ReportResponse

router = APIRouter(prefix="/cases/{case_id}/reports", tags=["Reports"])


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(
    case_id: UUID,
    body: ReportCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """UC-18: Queue contradiction report generation (FR-26)."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)

    report = Report(
        id=uuid.uuid4(),
        case_id=case_id,
        generated_by_id=current_user.id,
        title=body.title,
        report_type=body.report_type,
        format=body.format.upper(),
        status=ReportStatus.QUEUED,
        include_contradictions=body.include_contradictions,
        include_transcript_excerpts=body.include_transcript_excerpts,
        include_nl_query_log=body.include_nl_query_log,
    )
    db.add(report)
    await db.flush()

    try:
        from app.tasks.report import generate_report
        task = generate_report.delay(str(report.id))
        report.celery_task_id = task.id
    except Exception:
        pass  # Celery unavailable in dev

    return ReportResponse.model_validate(report)


@router.get("", response_model=PaginatedResponse)
async def list_reports(
    case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    query = select(Report).where(Report.case_id == case_id).order_by(Report.created_at.desc())
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    paginated = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    reports = paginated.scalars().all()
    return PaginatedResponse(
        items=[ReportResponse.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    case_id: UUID,
    report_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    from fastapi import HTTPException
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.case_id == case_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return ReportResponse.model_validate(report)
