"""
VeriDictum AI — Natural Language Query API
Handles FR-28 to FR-30 (NL case queries with citations).
"""

import math
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import _require_case_permission
from app.models import CasePermission, NLQuery, User
from app.schemas.case import NLQueryRequest, NLQueryResponse, PaginatedResponse
from app.services.query_service import answer_nl_query

router = APIRouter(prefix="/cases/{case_id}/query", tags=["NL Query"])


@router.post("", response_model=NLQueryResponse)
async def nl_query(
    case_id: UUID,
    body: NLQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NLQueryResponse:
    """FR-28/29: Natural language query against case corpus with cited sources."""
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)

    start = time.monotonic()
    answer, citations, tokens, model = await answer_nl_query(db, case_id, body.query)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Persist query log (FR-30)
    log = NLQuery(
        case_id=case_id,
        user_id=current_user.id,
        query_text=body.query,
        answer_text=answer,
        citations=citations,
        tokens_used=tokens,
        response_time_ms=elapsed_ms,
        model_used=model,
    )
    db.add(log)
    await db.flush()

    return NLQueryResponse.model_validate(log)


@router.get("/history", response_model=PaginatedResponse)
async def query_history(
    case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """FR-30: Retrieve logged NL queries for attorney review."""
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)

    query = select(NLQuery).where(NLQuery.case_id == case_id).order_by(NLQuery.created_at.desc())
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    paginated = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = paginated.scalars().all()

    return PaginatedResponse(
        items=[NLQueryResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )
