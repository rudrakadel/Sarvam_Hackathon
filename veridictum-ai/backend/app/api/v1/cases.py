from datetime import timezone
"""
VeriDictum AI — Cases API Router
Case CRUD, team management, audit log (FR-06 to FR-10, UC-13 to UC-18).
"""

import math
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_paralegal_or_above
from app.models import (
    AuditLog,
    Case,
    CaseMember,
    CasePermission,
    CaseStatus,
    User,
    UserRole,
)
from app.schemas.case import (
    AddMemberRequest,
    AuditLogResponse,
    CaseCreate,
    CaseMemberResponse,
    CaseResponse,
    CaseSummaryResponse,
    CaseUpdate,
    PaginatedResponse,
    UpdateMemberPermissionRequest,
)

router = APIRouter(prefix="/cases", tags=["Cases"])


async def _log_action(
    db: AsyncSession,
    user: User,
    action: str,
    case: Optional[Case] = None,
    details: Optional[dict] = None,
) -> None:
    log = AuditLog(
        user_id=user.id,
        organisation_id=user.organisation_id,
        case_id=case.id if case else None,
        action=action,
        details=details,
    )
    db.add(log)


# ---------------------------------------------------------------------------
# List / Create Cases
# ---------------------------------------------------------------------------
@router.get("", response_model=PaginatedResponse)
async def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[CaseStatus] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """List all cases accessible to current user in their organisation."""
    from sqlalchemy import or_
    query = select(Case).where(Case.organisation_id == current_user.organisation_id)
    if status:
        query = query.where(Case.status == status)
    if search:
        query = query.where(or_(
            Case.title.ilike(f"%{search}%"),
            Case.case_number.ilike(f"%{search}%"),
        ))

    if current_user.role != UserRole.ADMIN:
        # Non-admins see only cases they are members of
        query = query.join(CaseMember, CaseMember.case_id == Case.id).where(
            CaseMember.user_id == current_user.id
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.offset((page - 1) * page_size).limit(page_size).order_by(Case.created_at.desc())
    result = await db.execute(query)
    cases = result.scalars().all()

    return PaginatedResponse(
        items=[CaseSummaryResponse.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    current_user: User = Depends(require_paralegal_or_above),
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    """UC-13: Create a new legal case."""
    existing = await db.execute(
        select(Case).where(
            Case.organisation_id == current_user.organisation_id,
            Case.case_number == body.case_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Case number already exists in this organisation.")

    case = Case(
        organisation_id=current_user.organisation_id,
        created_by_id=current_user.id,
        **body.model_dump(),
    )
    db.add(case)
    await db.flush()

    # Grant CASE_OWNER to creator
    db.add(CaseMember(
        case_id=case.id,
        user_id=current_user.id,
        permission=CasePermission.CASE_OWNER,
    ))

    await _log_action(db, current_user, "CREATE_CASE", case, {"case_number": case.case_number})
    return CaseResponse.model_validate(case)


# ---------------------------------------------------------------------------
# Get / Update / Archive Single Case
# ---------------------------------------------------------------------------
@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    case = await _get_accessible_case(db, case_id, current_user)
    return CaseResponse.model_validate(case)


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    body: CaseUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CaseResponse:
    case = await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    await _log_action(db, current_user, "UPDATE_CASE", case)
    return CaseResponse.model_validate(case)


@router.post("/{case_id}/archive")
async def archive_case(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-17: Archive a closed case."""
    from datetime import datetime, timezone
    case = await _require_case_permission(db, case_id, current_user, CasePermission.CASE_OWNER)
    if case.status == CaseStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Case is already archived.")
    case.status = CaseStatus.ARCHIVED
    case.archived_at = datetime.now(timezone.utc)
    await _log_action(db, current_user, "ARCHIVE_CASE", case)
    return {"message": "Case archived successfully.", "status": "ARCHIVED"}


# ---------------------------------------------------------------------------
# Case Members
# ---------------------------------------------------------------------------
@router.get("/{case_id}/members", response_model=List[CaseMemberResponse])
async def list_members(
    case_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[CaseMemberResponse]:
    await _get_accessible_case(db, case_id, current_user)
    result = await db.execute(select(CaseMember).where(CaseMember.case_id == case_id).offset(skip).limit(limit))
    return [CaseMemberResponse.model_validate(m) for m in result.scalars()]


@router.post("/{case_id}/members", response_model=CaseMemberResponse, status_code=201)
async def add_member(
    case_id: UUID,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CaseMemberResponse:
    """UC-16: Assign case team member with permission."""
    await _require_case_permission(db, case_id, current_user, CasePermission.CASE_OWNER)

    # Check user belongs to same org
    user_result = await db.execute(
        select(User).where(User.id == body.user_id, User.organisation_id == current_user.organisation_id)
    )
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")

    existing = await db.execute(
        select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.user_id == body.user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member.")

    member = CaseMember(
        case_id=case_id,
        user_id=body.user_id,
        permission=body.permission,
        granted_by_id=current_user.id,
    )
    db.add(member)
    await _log_action(db, current_user, "ADD_CASE_MEMBER", None, {"user_id": str(body.user_id)})
    return CaseMemberResponse.model_validate(member)


@router.patch("/{case_id}/members/{user_id}")
async def update_member_permission(
    case_id: UUID,
    user_id: UUID,
    body: UpdateMemberPermissionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_case_permission(db, case_id, current_user, CasePermission.CASE_OWNER)
    result = await db.execute(
        select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    member.permission = body.permission
    return {"message": "Permission updated."}


@router.delete("/{case_id}/members/{user_id}")
async def remove_member(
    case_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_case_permission(db, case_id, current_user, CasePermission.CASE_OWNER)
    result = await db.execute(
        select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    await db.delete(member)
    return {"message": "Member removed."}


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
@router.get("/{case_id}/audit-log", response_model=PaginatedResponse)
async def get_audit_log(
    case_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """FR-09: Case-level audit log (UC-08)."""
    await _get_accessible_case(db, case_id, current_user)
    query = select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc())
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    paginated = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    logs = paginated.scalars().all()
    return PaginatedResponse(
        items=[AuditLogResponse.model_validate(l) for l in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_accessible_case(db: AsyncSession, case_id: UUID, user: User) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    if case.organisation_id != user.organisation_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    if user.role == UserRole.ADMIN:
        return case
    member_check = await db.execute(
        select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.user_id == user.id)
    )
    if not member_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You are not a member of this case.")
    return case


async def _require_case_permission(
    db: AsyncSession,
    case_id: UUID,
    user: User,
    required: CasePermission,
) -> Case:
    case = await _get_accessible_case(db, case_id, user)
    if user.role == UserRole.ADMIN:
        return case
    result = await db.execute(
        select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    order = {CasePermission.VIEWER: 0, CasePermission.EDITOR: 1, CasePermission.CASE_OWNER: 2}
    if not member or order[member.permission] < order[required]:
        raise HTTPException(status_code=403, detail="Insufficient case permission.")
    return case
