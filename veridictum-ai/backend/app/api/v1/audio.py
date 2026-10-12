"""
VeriDictum AI — Audio Upload & Transcription API
Handles FR-11 to FR-15 (audio ingestion, diarization, transcription, editing).
"""

import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.api.v1.cases import _require_case_permission
from app.models import AudioFile, CasePermission, ProcessingStatus, Transcript, TranscriptSegment, User
from app.schemas.case import (
    AudioFileResponse,
    EditSegmentRequest,
    SpeakerMappingRequest,
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from app.utils.storage import (
    build_audio_blob_name,
    compute_sha256,
    detect_mime_type,
    upload_blob,
)
from app.config import settings

router = APIRouter(prefix="/cases/{case_id}/audio", tags=["Audio & Transcription"])

ALLOWED_AUDIO_FORMATS = {"mp3", "mp4", "wav", "m4a", "ogg"}


# ---------------------------------------------------------------------------
# Upload Audio
# ---------------------------------------------------------------------------
@router.post("", response_model=AudioFileResponse, status_code=201)
async def upload_audio(
    case_id: UUID,
    file: UploadFile = File(...),
    language_hint: Optional[str] = Form(None),
    speaker_count_hint: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AudioFileResponse:
    """UC-19: Upload multi-speaker audio for transcription."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)

    # Validate format
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'. Allowed: {ALLOWED_AUDIO_FORMATS}")

    # Read and validate size
    data = await file.read()
    if len(data) > settings.MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 5 GB limit.")

    # Compute SHA-256
    sha256 = compute_sha256(data)

    audio_id = uuid.uuid4()
    blob_name = build_audio_blob_name(case_id, audio_id, file.filename)
    mime = detect_mime_type(file.filename)

    # Upload to local storage
    try:
        blob_path = upload_blob(
            settings.AZURE_STORAGE_CONTAINER_AUDIO,
            blob_name,
            data,
            content_type=mime,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    audio = AudioFile(
        id=audio_id,
        case_id=case_id,
        uploaded_by_id=current_user.id,
        original_filename=file.filename,
        blob_path=blob_path,
        file_size_bytes=len(data),
        format=ext,
        sha256_hash=sha256,
        mime_type=mime,
        language_hint=language_hint,
        speaker_count_hint=speaker_count_hint,
        status=ProcessingStatus.QUEUED,
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)

    # Enqueue transcription (try Celery first; if broker unavailable, dispatch in background)
    dispatched = False
    try:
        from app.tasks.transcription import transcribe_audio
        task = transcribe_audio.delay(str(audio.id))
        audio.celery_task_id = task.id
        await db.commit()
        dispatched = True
    except Exception:
        pass

    if not dispatched:
        from app.tasks.transcription import process_transcription
        background_tasks.add_task(process_transcription, str(audio.id))

    return AudioFileResponse.model_validate(audio)


@router.get("", response_model=List[AudioFileResponse])
async def list_audio(
    case_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[AudioFileResponse]:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(select(AudioFile).where(AudioFile.case_id == case_id).offset(skip).limit(limit))
    return [AudioFileResponse.model_validate(a) for a in result.scalars()]


@router.get("/{audio_id}", response_model=AudioFileResponse)
async def get_audio(
    case_id: UUID,
    audio_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AudioFileResponse:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    audio = await _get_audio(db, audio_id, case_id)
    return AudioFileResponse.model_validate(audio)


@router.post("/{audio_id}/retranscribe")
async def retranscribe(
    case_id: UUID,
    audio_id: UUID,
    language_hint: Optional[str] = None,
    speaker_count_hint: Optional[int] = None,
    audio_boost: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-25: Re-transcribe audio with corrected settings."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    audio = await _get_audio(db, audio_id, case_id)

    if language_hint:
        audio.language_hint = language_hint
    if speaker_count_hint:
        audio.speaker_count_hint = speaker_count_hint
    audio.audio_boost = audio_boost
    audio.status = ProcessingStatus.QUEUED
    await db.commit()

    task_id = None
    dispatched = False
    try:
        from app.tasks.transcription import transcribe_audio
        task = transcribe_audio.delay(str(audio.id))
        task_id = task.id
        audio.celery_task_id = task_id
        await db.commit()
        dispatched = True
    except Exception:
        pass

    if not dispatched:
        from app.tasks.transcription import process_transcription
        background_tasks.add_task(process_transcription, str(audio.id))

    return {"message": "Re-transcription queued.", "task_id": task_id}


# ---------------------------------------------------------------------------
# Transcript endpoints
# ---------------------------------------------------------------------------
@router.get("/{audio_id}/transcripts", response_model=List[TranscriptResponse])
async def list_transcripts(
    case_id: UUID,
    audio_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[TranscriptResponse]:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(Transcript).where(Transcript.audio_file_id == audio_id).order_by(Transcript.version.desc()).offset(skip).limit(limit)
    )
    return [TranscriptResponse.model_validate(t) for t in result.scalars()]


@router.get("/{audio_id}/transcripts/{transcript_id}/segments", response_model=List[TranscriptSegmentResponse])
async def get_segments(
    case_id: UUID,
    audio_id: UUID,
    transcript_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[TranscriptSegmentResponse]:
    await _require_case_permission(db, case_id, current_user, CasePermission.VIEWER)
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.segment_index)
    )
    return [TranscriptSegmentResponse.model_validate(s) for s in result.scalars()]


@router.patch("/{audio_id}/transcripts/{transcript_id}/segments/{segment_id}")
async def edit_segment(
    case_id: UUID,
    audio_id: UUID,
    transcript_id: UUID,
    segment_id: UUID,
    body: EditSegmentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-22: Inline transcript editing with change tracking."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    result = await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found.")

    if not segment.is_edited:
        segment.original_text = segment.text
    segment.text = body.text
    segment.is_edited = True

    # Mark transcript as edited
    transcript_result = await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    transcript = transcript_result.scalar_one_or_none()
    if transcript:
        transcript.is_edited = True

    return {"message": "Segment updated.", "segment_id": str(segment_id)}


@router.post("/{audio_id}/transcripts/{transcript_id}/speaker-labels")
async def set_speaker_labels(
    case_id: UUID,
    audio_id: UUID,
    transcript_id: UUID,
    body: SpeakerMappingRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-21: Map SPEAKER_XX labels to attorney-provided names."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    transcript.speaker_labels = body.mappings

    # Update segment speaker_name fields
    seg_result = await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id)
    )
    for seg in seg_result.scalars():
        if seg.speaker_label in body.mappings:
            seg.speaker_name = body.mappings[seg.speaker_label]

    return {"message": "Speaker labels updated."}


@router.post("/{audio_id}/transcripts/{transcript_id}/summarize")
async def summarize_transcript(
    case_id: UUID,
    audio_id: UUID,
    transcript_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UC-24: Generate or refresh an AI testimony summary via Sarvam LLM."""
    await _require_case_permission(db, case_id, current_user, CasePermission.EDITOR)
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    from app.tasks.transcription import _generate_sarvam_summary
    summary = _generate_sarvam_summary(transcript.full_text or "")
    transcript.summary = summary
    await db.commit()

    return {"message": "AI summary generated successfully.", "summary": summary}



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_audio(db: AsyncSession, audio_id: UUID, case_id: UUID) -> AudioFile:
    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id, AudioFile.case_id == case_id)
    )
    audio = result.scalar_one_or_none()
    if not audio:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return audio
