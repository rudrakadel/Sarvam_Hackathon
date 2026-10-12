"""
VeriDictum AI — Case & CaseMember SQLAlchemy ORM Models
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, JSONText, UUIDString


class CaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    VERDICT_ENTERED = "VERDICT_ENTERED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class CaseType(str, Enum):
    CRIMINAL = "CRIMINAL"
    CIVIL = "CIVIL"
    DEPOSITION = "DEPOSITION"
    ARBITRATION = "ARBITRATION"
    HEARING = "HEARING"
    OTHER = "OTHER"


class CasePermission(str, Enum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    CASE_OWNER = "CASE_OWNER"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    organisation_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    case_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    court: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    case_type: Mapped[str] = mapped_column(String(50), nullable=False, default=CaseType.OTHER.value)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=CaseStatus.OPEN.value)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parties: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    tags: Mapped[Any] = mapped_column(JSONText, nullable=False, default=list)
    storage_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[List["CaseMember"]] = relationship("CaseMember", back_populates="case", cascade="all, delete-orphan")


class CaseMember(Base):
    __tablename__ = "case_members"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission: Mapped[str] = mapped_column(String(50), nullable=False, default=CasePermission.VIEWER.value)
    added_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    case: Mapped["Case"] = relationship("Case", back_populates="members")
