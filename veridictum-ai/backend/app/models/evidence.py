"""
VeriDictum AI — Evidence (Audio, Transcript, Document) SQLAlchemy ORM Models
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, JSONText, UUIDString


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    DIARIZATION_COMPLETE = "DIARIZATION_COMPLETE"
    TRANSCRIBING = "TRANSCRIBING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


AudioStatus = ProcessingStatus
DocumentStatus = ProcessingStatus


class AudioFile(Base):
    __tablename__ = "audio_files"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    format: Mapped[str] = mapped_column(String(50), nullable=False, default="wav")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="audio/wav")
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessingStatus.PENDING.value)
    language_hint: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    speaker_count_hint: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def blob_name(self) -> str:
        return self.blob_path

    @blob_name.setter
    def blob_name(self, value: str) -> None:
        self.blob_path = value

    @property
    def processing_status(self) -> str:
        return self.status

    @processing_status.setter
    def processing_status(self, value: str) -> None:
        self.status = value


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    audio_file_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessingStatus.COMPLETE.value)
    language_detected: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False, default="whisper-large-v3")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    speaker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    segments: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    speaker_labels: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    whisper_wer_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diarization_der: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    speaker_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    words: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    format: Mapped[str] = mapped_column(String(50), nullable=False, default="pdf")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    document_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessingStatus.PENDING.value)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avg_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    has_handwriting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def blob_name(self) -> str:
        return self.blob_path

    @blob_name.setter
    def blob_name(self, value: str) -> None:
        self.blob_path = value

    @property
    def processing_status(self) -> str:
        return self.status

    @processing_status.setter
    def processing_status(self, value: str) -> None:
        self.status = value


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[str] = mapped_column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(UUIDString, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounding_boxes: Mapped[Optional[Any]] = mapped_column(JSONText, nullable=True)
    is_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    corrected_by_id: Mapped[Optional[str]] = mapped_column(UUIDString, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
