"""Phase B — case-level voice ↔ document audit for VeriDictum AI.

Per the PDF spec for project_01 (VeriDictum AI — the voice ↔ doc contradiction
flagship per the audit):
    "Aggregates confirmed and AI-suggested contradictions across a case's
     audio transcripts + document corpus. Flags severity drift between
     AI-suggested and attorney-confirmed contradictions, surfaces evidence
     gaps (audio without contradiction analysis run, documents not indexed),
     and produces a courtroom-ready audit brief."

This service:
- Reads every Contradiction row + Transcript + Document for the case
- Bucketises contradictions by status × severity → contradiction matrix
- Detects severity-drift signals (AI flagged HIGH but attorney downgraded to
  LOW more than 30% of the time → AI is over-flagging)
- Detects evidence gaps: audio with status != COMPLETE, documents without
  ocr_text, AnalysisJobs that errored
- Returns matrix + drift + gaps + talking_points
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


_SEVERITY_RANK = {
    "CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFORMATIONAL": 0,
}


def build_contradiction_matrix(
    contradictions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Bucket contradictions by status × severity.

    Returns:
        {
          "total": N,
          "by_status": {STATUS: N},
          "by_severity": {SEVERITY: N},
          "by_status_severity": {STATUS: {SEVERITY: N}},
          "confirmed_critical": N,
          "ai_suggested_unreviewed_critical": N,
          "confirmed_pct": float,
        }
    """
    matrix: Dict[str, Dict[str, int]] = {}
    by_status: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    total = 0
    confirmed_critical = 0
    ai_suggested_unreviewed_critical = 0
    confirmed = 0

    for c in contradictions:
        status = (c.get("status") or "AI_SUGGESTED").upper()
        sev = (c.get("severity") or "MEDIUM").upper()
        matrix.setdefault(status, {}).setdefault(sev, 0)
        matrix[status][sev] += 1
        by_status[status] = by_status.get(status, 0) + 1
        by_severity[sev] = by_severity.get(sev, 0) + 1
        total += 1
        if status == "CONFIRMED":
            confirmed += 1
            if sev in {"CRITICAL", "HIGH"}:
                confirmed_critical += 1
        elif status == "AI_SUGGESTED" and sev in {"CRITICAL", "HIGH"}:
            ai_suggested_unreviewed_critical += 1

    confirmed_pct = (confirmed / total * 100) if total else 0.0
    return {
        "total": total,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_status_severity": matrix,
        "confirmed_critical": confirmed_critical,
        "ai_suggested_unreviewed_critical": ai_suggested_unreviewed_critical,
        "confirmed_pct": round(confirmed_pct, 1),
    }


def detect_severity_drift(
    contradictions: List[Dict[str, Any]],
    over_flag_threshold_pct: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """If > 30% of attorney-reviewed contradictions were REJECTED, the AI is over-flagging.

    Equally, if attorney-confirmed contradictions skew higher severity than
    AI-suggested, AI is under-flagging.
    """
    reviewed = [c for c in contradictions if (c.get("status") or "").upper() in {"CONFIRMED", "REJECTED", "ANNOTATED"}]
    if len(reviewed) < 5:
        return None
    rejected = [c for c in reviewed if (c.get("status") or "").upper() == "REJECTED"]
    reject_pct = len(rejected) / len(reviewed) * 100
    if reject_pct > over_flag_threshold_pct:
        return {
            "type": "ai_over_flagging",
            "reviewed_count": len(reviewed),
            "rejected_count": len(rejected),
            "reject_pct": round(reject_pct, 1),
            "severity": "medium",
            "note": (
                f"{reject_pct:.0f}% of reviewed contradictions were REJECTED by attorneys — "
                "AI is over-flagging. Tune the confidence threshold or re-train on this case's corpus."
            ),
        }
    confirmed = [c for c in reviewed if (c.get("status") or "").upper() == "CONFIRMED"]
    if not confirmed:
        return None
    confirmed_avg = sum(_SEVERITY_RANK.get((c.get("severity") or "").upper(), 0) for c in confirmed) / len(confirmed)
    ai_sugg = [c for c in contradictions if (c.get("status") or "").upper() == "AI_SUGGESTED"]
    if not ai_sugg:
        return None
    ai_avg = sum(_SEVERITY_RANK.get((c.get("severity") or "").upper(), 0) for c in ai_sugg) / len(ai_sugg)
    if confirmed_avg > ai_avg + 0.7:
        return {
            "type": "ai_under_flagging",
            "confirmed_avg_severity": round(confirmed_avg, 2),
            "ai_avg_severity": round(ai_avg, 2),
            "severity": "high",
            "note": (
                f"Attorney-confirmed contradictions average severity {confirmed_avg:.2f} vs "
                f"AI-suggested {ai_avg:.2f}. AI is under-classifying — escalate review on "
                "AI-suggested rows before trial."
            ),
        }
    return None


def detect_evidence_gaps(
    audio_files: List[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    analysis_jobs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Audio not transcribed, documents not OCR'd, jobs that errored."""
    out: list[dict] = []
    incomplete_audio = [
        a for a in audio_files
        if (a.get("status") or "").upper() not in {"COMPLETE", "INDEXING"}
    ]
    if incomplete_audio:
        out.append({
            "type": "audio_not_transcribed",
            "count": len(incomplete_audio),
            "severity": "high",
            "note": (
                f"{len(incomplete_audio)} audio file(s) not yet COMPLETE — contradiction "
                "analysis is missing data. Re-run transcription before final brief."
            ),
        })
    docs_no_ocr = [
        d for d in documents
        if not (d.get("ocr_text") or d.get("indexed_at"))
    ]
    if docs_no_ocr:
        out.append({
            "type": "documents_not_indexed",
            "count": len(docs_no_ocr),
            "severity": "high",
            "note": (
                f"{len(docs_no_ocr)} document(s) lack OCR / index data — contradiction "
                "engine couldn't search them. Re-run OCR before final brief."
            ),
        })
    failed_jobs = [
        j for j in analysis_jobs
        if (j.get("status") or "").upper() in {"FAILED", "ERRORED"}
    ]
    if failed_jobs:
        out.append({
            "type": "analysis_jobs_failed",
            "count": len(failed_jobs),
            "severity": "medium",
            "note": (
                f"{len(failed_jobs)} contradiction analysis job(s) FAILED — re-run + diagnose "
                "before relying on the case's contradiction set."
            ),
        })
    return out


def detect_low_confidence_critical(
    contradictions: List[Dict[str, Any]],
    confidence_floor: float = 0.65,
) -> List[Dict[str, Any]]:
    """Contradictions tagged CRITICAL but with confidence below floor — flag for review."""
    out: list[dict] = []
    for c in contradictions:
        sev = (c.get("severity") or "").upper()
        if sev not in {"CRITICAL", "HIGH"}:
            continue
        conf = c.get("confidence_score") or 0.0
        if conf < confidence_floor:
            out.append({
                "contradiction_id": str(c.get("id")),
                "severity": sev,
                "confidence": conf,
                "transcript_excerpt": (c.get("transcript_text") or "")[:160],
                "document_excerpt": (c.get("document_text") or "")[:160],
                "note": (
                    f"Critical/high contradiction with confidence {conf:.2f} (below {confidence_floor:.2f}) — "
                    "review evidence before relying on it in court."
                ),
            })
    return out[:10]


class CourtroomAuditAnalyzer:
    def __init__(self) -> None:
        self.mock_mode = (
            os.environ.get("MOCK_FRAUD_GPT", "").lower() in {"1", "true", "yes"}
            or not os.environ.get("OPENAI_API_KEY")
        )

    async def analyze(
        self,
        case: Dict[str, Any],
        contradictions: List[Dict[str, Any]],
        audio_files: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        analysis_jobs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not contradictions and not audio_files and not documents:
            return {
                "mode": "no_content",
                "matrix": {},
                "severity_drift": None,
                "evidence_gaps": [],
                "low_confidence_critical": [],
                "talking_points": [],
            }

        matrix = build_contradiction_matrix(contradictions)
        drift = detect_severity_drift(contradictions)
        gaps = detect_evidence_gaps(audio_files, documents, analysis_jobs)
        low_conf = detect_low_confidence_critical(contradictions)

        talking_points: list[dict] = []
        if matrix["ai_suggested_unreviewed_critical"] > 0:
            talking_points.append({
                "topic": "unreviewed_critical",
                "severity": "critical",
                "point": (
                    f"{matrix['ai_suggested_unreviewed_critical']} CRITICAL/HIGH contradiction(s) "
                    "still AI_SUGGESTED — attorney review required before trial."
                ),
            })
        if drift:
            talking_points.append({
                "topic": drift["type"],
                "severity": drift.get("severity", "medium"),
                "point": drift["note"],
            })
        for g in gaps:
            talking_points.append({
                "topic": g["type"],
                "severity": g.get("severity", "medium"),
                "point": g["note"],
            })
        if low_conf:
            talking_points.append({
                "topic": "low_confidence_critical",
                "severity": "high",
                "point": (
                    f"{len(low_conf)} CRITICAL/HIGH contradiction(s) below 0.65 confidence — "
                    "evidence may not withstand cross-examination."
                ),
            })
        if matrix["confirmed_critical"] > 0:
            talking_points.append({
                "topic": "trial_ready_contradictions",
                "severity": "info",
                "point": (
                    f"{matrix['confirmed_critical']} attorney-CONFIRMED CRITICAL/HIGH "
                    "contradiction(s) — trial-ready evidence pool."
                ),
            })
        if not talking_points:
            talking_points.append({
                "topic": "summary",
                "severity": "info",
                "point": "Case audit clean — no unreviewed criticals, no drift, no evidence gaps.",
            })

        return {
            "mode": "deterministic",
            "matrix": matrix,
            "severity_drift": drift,
            "evidence_gaps": gaps,
            "low_confidence_critical": low_conf,
            "talking_points": talking_points,
        }
