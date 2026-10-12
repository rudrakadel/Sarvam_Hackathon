"""
VeriDictum AI — Contradiction Analysis Celery Task
GPT-4.1-nano semantic cross-referencing of transcript vs documents.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List

from openai import OpenAI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnalysisJob,
    Case,
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    Document,
    Transcript,
    TranscriptSegment,
)
from app.tasks.celery_app import celery_app
from app.websocket.pubsub import publish_job_update_sync, publish_case_event_sync

logger = logging.getLogger(__name__)


def _get_db_session() -> Session:
    engine = create_engine(settings.SYNC_DATABASE_URL)
    return Session(engine)


CONTRADICTION_SYSTEM_PROMPT = """You are a legal contradiction analysis AI for Sarvam Nyaya, a courtroom intelligence platform.

Your task: Identify SEMANTIC contradictions between spoken testimony (from transcripts) and written evidence (from documents).

A contradiction is when a speaker's statement in the transcript conflicts with factual content in the documents — differences in dates, locations, identities, actions, numbers, or facts stated as definitive by one source but contradicted by another.

Do NOT flag:
- Minor phrasing differences
- Vague or hedged statements
- Information only present in one source (that's a gap, not a contradiction)

For each contradiction found, return JSON with:
{
  "contradictions": [
    {
      "transcript_text": "exact quote from transcript",
      "transcript_speaker": "speaker name or label",
      "transcript_timestamp_start": 0.0,
      "document_text": "exact quote from document",
      "document_page": 1,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL",
      "confidence_score": 0.95,
      "explanation": "Clear one-paragraph explanation of the contradiction",
      "contradiction_type": "factual|temporal|identity|numeric|geographic"
    }
  ]
}

Severity guide:
- CRITICAL: Direct perjury indicator — witness denies documented fact under oath
- HIGH: Clear factual conflict that could determine case outcome
- MEDIUM: Significant inconsistency that warrants attorney attention
- LOW: Minor discrepancy that may have innocent explanation
- INFORMATIONAL: Noteworthy difference, not necessarily contradictory

All output must be valid JSON. Include ALL contradictions found, up to 50 per run.
Mark ALL results as AI_SUGGESTED — they require attorney review before use."""


def _build_analysis_prompt(transcript_segments: List[dict], document_texts: List[dict]) -> str:
    transcript_block = "\n".join(
        f"[{s['speaker']} at {s['start']:.1f}s]: {s['text']}"
        for s in transcript_segments[:200]  # limit context
    )
    doc_block = "\n\n".join(
        f"DOCUMENT: {d['name']} (Page {d['page']})\n{d['text']}"
        for d in document_texts[:20]
    )
    return f"""TRANSCRIPT SEGMENTS:
{transcript_block}

---

DOCUMENTARY EVIDENCE:
{doc_block}

Identify all semantic contradictions between the testimony and the documents. Return valid JSON only."""


@celery_app.task(
    name="app.tasks.contradiction.run_contradiction_analysis",
    bind=True,
    # Auto-retry on transient OpenAI failures (rate limits, 5xx, connection
    # drops). Exponential backoff with jitter prevents thundering-herd retries
    # against the upstream provider when a region briefly goes degraded.
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,   # cap individual sleeps at 10 min
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def run_contradiction_analysis(self, case_id: str, job_id: str) -> dict:
    """
    Cross-reference all transcripts vs documents in a case using GPT-4.1-nano.
    Detects semantic contradictions with severity scoring.
    """
    with _get_db_session() as db:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return {"status": "error"}

        job.status = "PROCESSING"
        db.commit()
        publish_job_update_sync(job_id, "PROCESSING", progress=0)

        try:
            # --- Gather transcripts ---
            transcripts = db.execute(
                select(Transcript).where(
                    Transcript.case_id == case_id,
                    Transcript.status == "COMPLETE",
                )
            ).scalars().all()

            if not transcripts:
                job.status = "COMPLETE"
                job.error_message = "No completed transcripts found."
                db.commit()
                return {"status": "no_transcripts"}

            # Build segment list
            all_segments = []
            transcript_map = {}
            for t in transcripts:
                segs = db.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == t.id)
                    .order_by(TranscriptSegment.segment_index)
                ).scalars().all()
                for seg in segs:
                    all_segments.append({
                        "id": str(seg.id),
                        "transcript_id": str(t.id),
                        "speaker": seg.speaker_name or seg.speaker_label,
                        "start": seg.start_time,
                        "end": seg.end_time,
                        "text": seg.text,
                    })
                    transcript_map[str(seg.id)] = {"transcript_id": str(t.id), "segment": seg}

            # --- Gather documents ---
            documents = db.execute(
                select(Document).where(
                    Document.case_id == case_id,
                    Document.status == "COMPLETE",
                )
            ).scalars().all()

            if not documents:
                job.status = "COMPLETE"
                job.error_message = "No completed documents found."
                db.commit()
                return {"status": "no_documents"}

            doc_texts = []
            doc_map = {}
            for doc in documents:
                if doc.extracted_text:
                    # Chunk into page-sized pieces
                    chunks = doc.extracted_text.split("--- PAGE BREAK ---")
                    for i, chunk in enumerate(chunks[:50]):
                        doc_texts.append({
                            "doc_id": str(doc.id),
                            "name": doc.original_filename,
                            "page": i + 1,
                            "text": chunk[:3000].strip(),
                        })
                        doc_map[f"{doc.id}_{i+1}"] = doc

            # --- LLM Analysis (OpenAI / Groq / Gemini / Ollama) ---
            client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL if settings.OPENAI_BASE_URL else None,
            )
            prompt = _build_analysis_prompt(all_segments, doc_texts)

            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": CONTRADICTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=8000,
            )

            tokens_used = response.usage.total_tokens if response.usage else 0
            result_json = json.loads(response.choices[0].message.content)
            contradictions_data = result_json.get("contradictions", [])

            # --- Persist contradictions ---
            saved = 0
            for c_data in contradictions_data:
                # Find matching segment by text
                matching_seg = None
                matching_transcript_id = None
                for seg_info in all_segments:
                    if seg_info["text"].strip()[:100] in c_data.get("transcript_text", ""):
                        matching_seg = transcript_map.get(seg_info["id"], {}).get("segment")
                        matching_transcript_id = seg_info["transcript_id"]
                        break

                # Find matching document
                matching_doc = None
                for d in documents:
                    if d.original_filename in c_data.get("document_text", "") or \
                       c_data.get("document_text", "")[:50] in (d.extracted_text or ""):
                        matching_doc = d
                        break
                if not matching_doc and documents:
                    matching_doc = documents[0]

                try:
                    severity = ContradictionSeverity(c_data.get("severity", "MEDIUM"))
                except ValueError:
                    severity = ContradictionSeverity.MEDIUM

                contradiction = Contradiction(
                    case_id=case_id,
                    analysis_job_id=job.id,
                    transcript_id=matching_transcript_id,
                    segment_id=str(matching_seg.id) if matching_seg else None,
                    transcript_text=c_data.get("transcript_text", "")[:2000],
                    transcript_speaker=c_data.get("transcript_speaker"),
                    transcript_timestamp_start=c_data.get("transcript_timestamp_start"),
                    document_id=str(matching_doc.id) if matching_doc else None,
                    document_page=c_data.get("document_page"),
                    document_text=c_data.get("document_text", "")[:2000],
                    severity=severity,
                    confidence_score=min(1.0, max(0.0, float(c_data.get("confidence_score", 0.7)))),
                    explanation=c_data.get("explanation", "")[:3000],
                    contradiction_type=c_data.get("contradiction_type"),
                    status=ContradictionStatus.AI_SUGGESTED,
                )
                db.add(contradiction)
                saved += 1

            job.status = "COMPLETE"
            job.total_contradictions_found = saved
            job.tokens_used = tokens_used
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

            publish_job_update_sync(job_id, "COMPLETE", progress=100, total_contradictions=saved)
            publish_case_event_sync(case_id, "analysis_complete", {
                "job_id": job_id,
                "total_contradictions_found": saved,
            })

            logger.info(f"Contradiction analysis complete for case {case_id}: {saved} found")
            return {"status": "complete", "contradictions_found": saved}

        except Exception as exc:
            logger.exception(f"Contradiction analysis failed for case {case_id}: {exc}")
            job.status = "FAILED"
            job.error_message = str(exc)[:1000]
            db.commit()
            publish_job_update_sync(job_id, "FAILED", error=str(exc)[:200])
            raise self.retry(exc=exc, countdown=60)
