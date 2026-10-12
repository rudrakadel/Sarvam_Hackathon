"""
VeriDictum AI — Case & Evidence Pydantic Schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.case import CasePermission, CaseStatus, CaseType


# --- Cases ---
class CaseCreate(BaseModel):
    case_number: str
    title: str
    court: Optional[str] = None
    jurisdiction: Optional[str] = None
    case_type: CaseType = CaseType.OTHER
    parties: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    court: Optional[str] = None
    jurisdiction: Optional[str] = None
    case_type: Optional[CaseType] = None
    parties: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[CaseStatus] = None


class CaseResponse(BaseModel):
    id: UUID
    organisation_id: UUID
    case_number: str
    title: str
    court: Optional[str]
    jurisdiction: Optional[str]
    case_type: CaseType
    parties: Optional[Dict[str, Any]]
    status: CaseStatus
    tags: Optional[List[str]]
    storage_used_bytes: int
    created_at: datetime
    updated_at: Optional[datetime]
    archived_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CaseSummaryResponse(BaseModel):
    id: UUID
    case_number: str
    title: str
    case_type: CaseType
    status: CaseStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Case Members ---
class AddMemberRequest(BaseModel):
    user_id: UUID
    permission: CasePermission = CasePermission.VIEWER


class UpdateMemberPermissionRequest(BaseModel):
    permission: CasePermission


class CaseMemberResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    permission: CasePermission
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Audio ---
class AudioFileResponse(BaseModel):
    id: UUID
    case_id: UUID
    original_filename: str
    file_size_bytes: int
    duration_seconds: Optional[float]
    format: str
    status: str
    language_hint: Optional[str]
    speaker_count_hint: Optional[int]
    audio_quality_score: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Documents ---
class DocumentResponse(BaseModel):
    id: UUID
    case_id: UUID
    original_filename: str
    file_size_bytes: int
    format: str
    status: str
    document_type: Optional[str]
    page_count: Optional[int]
    avg_confidence: Optional[float]
    has_handwriting: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Transcripts ---
class SpeakerMappingRequest(BaseModel):
    mappings: Dict[str, str]    # {"SPEAKER_00": "John Smith", ...}


class TranscriptSegmentResponse(BaseModel):
    id: UUID
    segment_index: int
    speaker_label: str
    speaker_name: Optional[str]
    start_time: float
    end_time: float
    text: str
    confidence: Optional[float]
    is_edited: bool

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    id: UUID
    audio_file_id: UUID
    version: int
    status: str
    full_text: Optional[str]
    word_count: Optional[int]
    speaker_count: Optional[int]
    speaker_labels: Optional[Dict[str, str]]
    is_edited: bool
    is_indexed: bool
    summary: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EditSegmentRequest(BaseModel):
    text: str


# --- Contradictions ---
class ContradictionReviewRequest(BaseModel):
    status: str      # CONFIRMED | REJECTED | ANNOTATED
    attorney_notes: Optional[str] = None


class ContradictionResponse(BaseModel):
    id: UUID
    case_id: UUID
    transcript_text: str
    transcript_speaker: Optional[str]
    transcript_timestamp_start: Optional[float]
    document_text: str
    document_page: Optional[int]
    severity: str
    confidence_score: float
    explanation: str
    contradiction_type: Optional[str]
    status: str
    attorney_notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- NL Queries ---
class NLQueryRequest(BaseModel):
    query: str


class CitationResponse(BaseModel):
    source_type: str           # "transcript" | "document"
    source_id: str
    speaker: Optional[str]
    timestamp: Optional[float]
    page: Optional[int]
    excerpt: str


class NLQueryResponse(BaseModel):
    id: UUID
    query_text: str
    answer_text: str
    citations: Optional[List[Dict]]
    response_time_ms: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Reports ---
class ReportCreateRequest(BaseModel):
    title: str
    report_type: str = "FULL_SUMMARY"
    format: str = "PDF"
    include_contradictions: bool = True
    include_transcript_excerpts: bool = True
    include_nl_query_log: bool = False


class ReportResponse(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    report_type: str
    format: str
    status: str
    download_url: Optional[str]
    page_count: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# --- Audit log ---
class AuditLogResponse(BaseModel):
    id: UUID
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[Dict]
    ip_address: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Pagination ---
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
