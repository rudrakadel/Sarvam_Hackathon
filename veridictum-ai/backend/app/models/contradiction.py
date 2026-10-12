"""
VeriDictum AI — Contradiction, AnalysisJob, Report, NLQuery, and AuditLog SQLAlchemy ORM Models
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, JSONText, UUIDString


class ContradictionSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"
    INFO = "INFO"


class ContradictionStatus(str, Enum):
    AI_SUGGESTED = "AI_SUGGESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    ANNOTATED = "ANNOTATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReportStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    READY = "READY"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_job_id: Mapped[Optional[str]] = mapped_column(UUIDString, nullable=True)
    transcript_id: Mapped[Optional[str]] = mapped_column(UUIDString, nullable=True)
    segment_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default=ContradictionSeverity.MEDIUM.value)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ContradictionStatus.AI_SUGGESTED.value)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contradiction_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_speaker: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    transcript_timestamp_start: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    document_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attorney_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def ai_confidence(self) -> float:
        return self.confidence_score

    @ai_confidence.setter
    def ai_confidence(self, val: float) -> None:
        self.confidence_score = val

    @property
    def ai_explanation(self) -> str:
        return self.explanation

    @ai_explanation.setter
    def ai_explanation(self, val: str) -> None:
        self.explanation = val

    @property
    def attorney_note(self) -> Optional[str]:
        return self.attorney_notes

    @attorney_note.setter
    def attorney_note(self, val: Optional[str]) -> None:
        self.attorney_notes = val


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    triggered_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    total_contradictions_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def contradictions_found(self) -> int:
        return self.total_contradictions_found

    @contradictions_found.setter
    def contradictions_found(self, val: int) -> None:
        self.total_contradictions_found = val


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False, default="FULL_SUMMARY")
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="PDF")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ReportStatus.QUEUED.value)
    blob_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    sas_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    include_contradictions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_transcript_excerpts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_nl_query_log: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def blob_name(self) -> Optional[str]:
        return self.blob_path

    @blob_name.setter
    def blob_name(self, val: Optional[str]) -> None:
        self.blob_path = val

    @property
    def sas_url(self) -> Optional[str]:
        return self.download_url

    @sas_url.setter
    def sas_url(self, val: Optional[str]) -> None:
        self.download_url = val


class NLQuery(Base):
    __tablename__ = "nl_queries"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citations: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True, default=list)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    retrieval_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    organisation_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    case_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def details(self) -> Optional[Any]:
        return self.detail

    @details.setter
    def details(self, val: Optional[Any]) -> None:
        self.detail = val
