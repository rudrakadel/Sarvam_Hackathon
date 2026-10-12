/**
 * VeriDictum AI — Shared TypeScript Types
 * Mirrors the backend Pydantic schemas for type-safety across the stack.
 */

// ─────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginRequest {
  email: string;
  password: string;
  totp_code?: string;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  // Backend field name (see backend/app/schemas/auth.py:25). Keep aligned —
  // a previous mismatch (`firm_name`) caused every signup to 422.
  organisation_name: string;
}

// ─────────────────────────────────────────────
// User
// ─────────────────────────────────────────────
export type UserRole = "ADMIN" | "ATTORNEY" | "PARALEGAL" | "VIEWER";
export type AccountStatus = "PENDING" | "ACTIVE" | "SUSPENDED" | "DEACTIVATED" | "LOCKED";

export interface User {
  id: string;
  organisation_id: string;
  full_name: string;
  email: string;
  role: UserRole;
  status: AccountStatus;
  email_verified: boolean;
  mfa_enabled: boolean;
  phone?: string;
  last_login?: string;
  created_at: string;
}

// ─────────────────────────────────────────────
// Organisation
// ─────────────────────────────────────────────
export type SubscriptionTier = "STARTER" | "PROFESSIONAL" | "ENTERPRISE" | "PUBLIC_DEFENDER";

export interface Organisation {
  id: string;
  name: string;
  domain?: string;
  subscription_tier: SubscriptionTier;
  is_active: boolean;
  sso_enabled: boolean;
  storage_quota_bytes: number;
  storage_used_bytes: number;
  max_cases: number;
  max_users: number;
  created_at: string;
}

// ─────────────────────────────────────────────
// Cases
// ─────────────────────────────────────────────
export type CaseStatus = "OPEN" | "IN_REVIEW" | "VERDICT_ENTERED" | "ARCHIVED";
export type CaseType = "CRIMINAL" | "CIVIL" | "DEPOSITION" | "ARBITRATION" | "HEARING" | "OTHER";
export type CasePermission = "VIEWER" | "EDITOR" | "CASE_OWNER";

export interface Case {
  id: string;
  organisation_id: string;
  case_number: string;
  title: string;
  court?: string;
  jurisdiction?: string;
  case_type: CaseType;
  parties?: Record<string, string>;
  status: CaseStatus;
  tags?: string[];
  storage_used_bytes: number;
  created_at: string;
  updated_at?: string;
  archived_at?: string;
}

export interface CaseMember {
  id: string;
  case_id: string;
  user_id: string;
  permission: CasePermission;
  created_at: string;
}

// ─────────────────────────────────────────────
// Audio & Transcription
// ─────────────────────────────────────────────
export type ProcessingStatus =
  | "QUEUED" | "PROCESSING" | "DIARIZATION_COMPLETE"
  | "TRANSCRIBING" | "INDEXING" | "COMPLETE" | "FAILED" | "RETRYING";

export interface AudioFile {
  id: string;
  case_id: string;
  original_filename: string;
  file_size_bytes: number;
  duration_seconds?: number;
  format: string;
  status: ProcessingStatus;
  language_hint?: string;
  speaker_count_hint?: number;
  audio_quality_score?: number;
  created_at: string;
}

export interface TranscriptSegment {
  id: string;
  segment_index: number;
  speaker_label: string;
  speaker_name?: string;
  start_time: number;
  end_time: number;
  text: string;
  confidence?: number;
  is_edited: boolean;
}

export interface Transcript {
  id: string;
  audio_file_id: string;
  version: number;
  status: ProcessingStatus;
  full_text?: string;
  word_count?: number;
  speaker_count?: number;
  speaker_labels?: Record<string, string>;
  summary?: string;
  is_edited: boolean;
  is_indexed: boolean;
  created_at: string;
}

// ─────────────────────────────────────────────
// Documents
// ─────────────────────────────────────────────
export interface Document {
  id: string;
  case_id: string;
  original_filename: string;
  file_size_bytes: number;
  format: string;
  status: ProcessingStatus;
  document_type?: string;
  page_count?: number;
  avg_confidence?: number;
  has_handwriting: boolean;
  created_at: string;
}

// ─────────────────────────────────────────────
// Contradictions
// ─────────────────────────────────────────────
export type ContradictionSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL";
export type ContradictionStatus = "AI_SUGGESTED" | "CONFIRMED" | "REJECTED" | "ANNOTATED";

export interface Contradiction {
  id: string;
  case_id: string;
  transcript_text: string;
  transcript_speaker?: string;
  transcript_timestamp_start?: number;
  document_text: string;
  document_page?: number;
  severity: ContradictionSeverity;
  confidence_score: number;
  explanation: string;
  contradiction_type?: string;
  status: ContradictionStatus;
  attorney_notes?: string;
  created_at: string;
}

export interface ContradictionStats {
  total: number;
  by_severity: Record<ContradictionSeverity, number>;
  by_status: Record<ContradictionStatus, number>;
  pending_review: number;
  avg_confidence?: number;
}

// ─────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────
export type ReportStatus = "QUEUED" | "GENERATING" | "COMPLETE" | "FAILED";

export interface Report {
  id: string;
  case_id: string;
  title: string;
  report_type: string;
  format: string;
  status: ReportStatus;
  download_url?: string;
  page_count?: number;
  created_at: string;
  completed_at?: string;
}

// ─────────────────────────────────────────────
// NL Query
// ─────────────────────────────────────────────
export interface NLQuery {
  id: string;
  query_text: string;
  answer_text: string;
  citations?: Array<{
    source_type: string;
    source_id?: string;
    speaker?: string;
    timestamp?: number;
    page?: number;
    excerpt?: string;
  }>;
  response_time_ms?: number;
  created_at: string;
}

// ─────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────
export type NotificationType =
  | "ANALYSIS_COMPLETE"
  | "ANALYSIS_FAILED"
  | "TRANSCRIPT_READY"
  | "OCR_COMPLETE"
  | "REPORT_READY"
  | "CASE_SHARED"
  | "SYSTEM";

export interface Notification {
  id: string;
  user_id: string;
  case_id?: string;
  type: NotificationType;
  title: string;
  body?: string;
  is_read: boolean;
  created_at: string;
  read_at?: string;
}

// ─────────────────────────────────────────────
// Dashboard
// ─────────────────────────────────────────────
export interface DashboardStats {
  cases: {
    total: number;
    by_status: Record<string, number>;
    open: number;
    in_review: number;
    archived: number;
  };
  contradictions: {
    total: number;
    critical: number;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
    pending_review: number;
  };
  evidence: {
    total_audio: number;
    total_documents: number;
    audio_in_queue: number;
    documents_in_queue: number;
    total_in_queue: number;
  };
  reports: {
    by_status: Record<string, number>;
    total: number;
    complete: number;
  };
  recent_analysis_jobs: Array<{
    id: string;
    case_id: string;
    status: string;
    total_contradictions_found: number;
    created_at: string;
    completed_at?: string;
  }>;
}

// ─────────────────────────────────────────────
// API
// ─────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  detail: string;
}
