"""Phase B + C tests for VeriDictum — courtroom audit + brief PDF."""
from __future__ import annotations

import os
import uuid

import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_fraud_gpt():
    os.environ["MOCK_FRAUD_GPT"] = "true"
    yield
    os.environ.pop("MOCK_FRAUD_GPT", None)


# ---- unit tests --------------------------------------------------------


async def test_matrix_drift_and_gaps():
    from app.services.courtroom_audit_analyzer import (
        build_contradiction_matrix,
        detect_severity_drift,
        detect_evidence_gaps,
        detect_low_confidence_critical,
        CourtroomAuditAnalyzer,
    )

    contras = [
        # Confirmed criticals
        {"id": "c1", "severity": "CRITICAL", "status": "CONFIRMED", "confidence_score": 0.92,
         "transcript_text": "T1", "document_text": "D1"},
        {"id": "c2", "severity": "HIGH", "status": "CONFIRMED", "confidence_score": 0.85,
         "transcript_text": "T2", "document_text": "D2"},
        # Unreviewed AI-suggested critical
        {"id": "c3", "severity": "CRITICAL", "status": "AI_SUGGESTED", "confidence_score": 0.60,
         "transcript_text": "T3", "document_text": "D3"},
        # 4 rejected — over-flagging signal
        {"id": "c4", "severity": "LOW", "status": "REJECTED", "confidence_score": 0.40,
         "transcript_text": "T4", "document_text": "D4"},
        {"id": "c5", "severity": "LOW", "status": "REJECTED", "confidence_score": 0.42,
         "transcript_text": "T5", "document_text": "D5"},
        {"id": "c6", "severity": "MEDIUM", "status": "REJECTED", "confidence_score": 0.48,
         "transcript_text": "T6", "document_text": "D6"},
        {"id": "c7", "severity": "MEDIUM", "status": "REJECTED", "confidence_score": 0.55,
         "transcript_text": "T7", "document_text": "D7"},
    ]

    matrix = build_contradiction_matrix(contras)
    assert matrix["total"] == 7
    assert matrix["confirmed_critical"] == 2
    assert matrix["ai_suggested_unreviewed_critical"] == 1
    assert matrix["by_status"]["CONFIRMED"] == 2
    assert matrix["by_status"]["REJECTED"] == 4

    drift = detect_severity_drift(contras)
    # 4 of 6 reviewed = 66% rejected → over-flagging
    assert drift is not None and drift["type"] == "ai_over_flagging"

    # Audio that hasn't been transcribed + doc without OCR + failed job → 3 gaps
    audios = [{"id": "a1", "status": "PROCESSING"}, {"id": "a2", "status": "COMPLETE"}]
    docs = [{"id": "d1", "ocr_text": ""}, {"id": "d2", "ocr_text": "hello"}]
    jobs = [{"id": "j1", "status": "FAILED"}]
    gaps = detect_evidence_gaps(audios, docs, jobs)
    types = {g["type"] for g in gaps}
    assert {"audio_not_transcribed", "documents_not_indexed", "analysis_jobs_failed"} == types

    low_conf = detect_low_confidence_critical(contras, confidence_floor=0.65)
    # c3 is CRITICAL @ 0.60 → flagged
    assert any(x["contradiction_id"] == "c3" for x in low_conf)

    analyzer = CourtroomAuditAnalyzer()
    result = await analyzer.analyze(
        {"id": "case1", "title": "Test Case", "status": "active"},
        contras, audios, docs, jobs,
    )
    assert result["mode"] == "deterministic"
    severities = {tp["severity"] for tp in result["talking_points"]}
    assert "critical" in severities


async def test_clean_case_returns_summary():
    from app.services.courtroom_audit_analyzer import CourtroomAuditAnalyzer
    analyzer = CourtroomAuditAnalyzer()
    result = await analyzer.analyze(
        {"id": "case1", "title": "Clean Case"},
        contradictions=[],
        audio_files=[{"id": "a1", "status": "COMPLETE"}],
        documents=[{"id": "d1", "ocr_text": "indexed"}],
        analysis_jobs=[{"id": "j1", "status": "COMPLETE"}],
    )
    topics = {tp["topic"] for tp in result["talking_points"]}
    assert "summary" in topics


async def test_empty_returns_no_content():
    from app.services.courtroom_audit_analyzer import CourtroomAuditAnalyzer
    analyzer = CourtroomAuditAnalyzer()
    result = await analyzer.analyze({}, [], [], [], [])
    assert result["mode"] == "no_content"


# ---- endpoint tests --------------------------------------------------------


async def _seed_case_with_contradictions(db, test_user):
    from app.models import (
        Case, CaseStatus, CaseType, Contradiction, ContradictionSeverity, ContradictionStatus,
    )
    case = Case(
        organisation_id=test_user.organisation_id,
        created_by_id=test_user.id,
        title=f"Test Case {uuid.uuid4().hex[:5]}",
        case_number=f"CN-{uuid.uuid4().hex[:8]}",
        case_type=CaseType.CIVIL,
        status=CaseStatus.OPEN,
    )
    db.add(case)
    await db.flush()

    # Three contradictions: 1 confirmed-critical, 1 AI-suggested-high, 1 rejected.
    db.add(Contradiction(
        case_id=case.id,
        transcript_text="Witness said the meeting was on March 12.",
        document_text="Calendar entry shows the meeting was on March 15.",
        severity=ContradictionSeverity.CRITICAL,
        confidence_score=0.92,
        explanation="Date mismatch between witness testimony and calendar.",
        status=ContradictionStatus.CONFIRMED,
    ))
    db.add(Contradiction(
        case_id=case.id,
        transcript_text="Witness said they signed at 5pm.",
        document_text="Signature timestamp is 3:42pm.",
        severity=ContradictionSeverity.HIGH,
        confidence_score=0.60,  # low confidence — should surface
        explanation="Time mismatch.",
        status=ContradictionStatus.AI_SUGGESTED,
    ))
    db.add(Contradiction(
        case_id=case.id,
        transcript_text="Witness said the car was red.",
        document_text="Photo shows the car was blue.",
        severity=ContradictionSeverity.LOW,
        confidence_score=0.40,
        explanation="Color discrepancy (likely lighting/photo quality).",
        status=ContradictionStatus.REJECTED,
    ))
    await db.flush()
    return case


async def test_courtroom_audit_endpoint(client, db, test_user, auth_headers):
    case = await _seed_case_with_contradictions(db, test_user)
    res = await client.post(
        f"/api/v1/cases/{case.id}/courtroom-audit",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "deterministic"
    assert body["contradictions_checked"] == 3
    # 1 confirmed critical
    assert body["matrix"]["confirmed_critical"] == 1
    # 1 unreviewed high
    assert body["matrix"]["ai_suggested_unreviewed_critical"] == 1
    # Low-confidence critical (the AI_SUGGESTED HIGH @ 0.60) should surface
    assert body["low_confidence_critical"]


async def test_courtroom_brief_pdf_renders(client, db, test_user, auth_headers):
    case = await _seed_case_with_contradictions(db, test_user)
    pdf = await client.get(
        f"/api/v1/cases/{case.id}/courtroom-brief.pdf",
        headers=auth_headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"
    assert "veridictum-brief-" in pdf.headers.get("content-disposition", "")
    assert pdf.headers.get("x-veridictum-mode") == "deterministic"


async def test_courtroom_audit_unknown_case_404(client, auth_headers):
    res = await client.post(
        "/api/v1/cases/00000000-0000-0000-0000-000000000000/courtroom-audit",
        headers=auth_headers,
    )
    # Some routers wrap the not-found in a 400 (permission-style); accept either.
    assert res.status_code in (404, 400)
