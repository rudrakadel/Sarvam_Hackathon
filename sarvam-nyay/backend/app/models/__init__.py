"""
VeriDictum AI — Models package registry.
Exports all SQLAlchemy ORM models and related enumerations.
"""

from app.models.case import (
    Case,
    CaseMember,
    CasePermission,
    CaseStatus,
    CaseType,
)
from app.models.contradiction import (
    AnalysisJob,
    AuditLog,
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    NLQuery,
    Report,
    ReportStatus,
)
from app.models.evidence import (
    AudioFile,
    AudioStatus,
    Document,
    DocumentPage,
    DocumentStatus,
    ProcessingStatus,
    Transcript,
    TranscriptSegment,
)
from app.models.notification import (
    Notification,
    NotificationType,
)
from app.models.user import (
    AccountStatus,
    Invitation,
    Organisation,
    RefreshToken,
    SubscriptionTier,
    User,
    UserRole,
)

__all__ = [
    "AccountStatus",
    "AnalysisJob",
    "AudioFile",
    "AudioStatus",
    "AuditLog",
    "Case",
    "CaseMember",
    "CasePermission",
    "CaseStatus",
    "CaseType",
    "Contradiction",
    "ContradictionSeverity",
    "ContradictionStatus",
    "Document",
    "DocumentPage",
    "DocumentStatus",
    "Invitation",
    "NLQuery",
    "Notification",
    "NotificationType",
    "Organisation",
    "ProcessingStatus",
    "RefreshToken",
    "Report",
    "ReportStatus",
    "SubscriptionTier",
    "Transcript",
    "TranscriptSegment",
    "User",
    "UserRole",
]
