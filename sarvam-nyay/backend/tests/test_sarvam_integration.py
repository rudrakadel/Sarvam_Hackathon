"""
Tests for Sarvam AI integration — STT & Sarvam Vision payload parsing and provider routing.
"""

import pytest

from app.config import settings
from app.tasks.transcription import _parse_sarvam_stt_result
from app.tasks.ocr import _parse_sarvam_vision_result, _process_with_local_pdf


def test_settings_sarvam_configuration():
    assert hasattr(settings, "SARVAM_API_KEY")
    assert hasattr(settings, "SARVAM_STT_MODEL")
    assert hasattr(settings, "SARVAM_VISION_MODEL")
    assert hasattr(settings, "STT_PROVIDER")
    assert hasattr(settings, "OCR_PROVIDER")
    assert hasattr(settings, "OPENAI_BASE_URL")
    assert settings.STT_PROVIDER in ["sarvam", "deepinfra"]
    assert settings.OCR_PROVIDER in ["sarvam", "azure", "local"]


def test_parse_sarvam_stt_diarized_transcript():
    sample_response = {
        "transcript": "Good morning your honor. Good morning counsel.",
        "diarized_transcript": {
            "entries": [
                {
                    "speaker_id": "SPEAKER_01",
                    "transcript": "Good morning your honor.",
                    "start_time_seconds": 0.5,
                    "end_time_seconds": 2.1,
                },
                {
                    "speaker_id": "SPEAKER_02",
                    "transcript": "Good morning counsel.",
                    "start_time_seconds": 2.3,
                    "end_time_seconds": 3.8,
                },
            ]
        },
    }

    full_text, segments = _parse_sarvam_stt_result(sample_response)
    assert full_text == "Good morning your honor. Good morning counsel."
    assert len(segments) == 2
    assert segments[0]["speaker"] == "SPEAKER_01"
    assert segments[0]["start"] == 0.5
    assert segments[0]["end"] == 2.1
    assert segments[0]["text"] == "Good morning your honor."
    assert segments[1]["speaker"] == "SPEAKER_02"
    assert segments[1]["text"] == "Good morning counsel."


def test_parse_sarvam_stt_plain_transcript():
    sample_response = {
        "transcript": "The light was green when I drove through the intersection.",
    }

    full_text, segments = _parse_sarvam_stt_result(sample_response)
    assert "The light was green" in full_text
    assert len(segments) == 1
    assert segments[0]["speaker"] == "SPEAKER_00"
    assert segments[0]["text"] == "The light was green when I drove through the intersection."


def test_parse_sarvam_vision_pages_and_polygons():
    sample_vision_response = {
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "text": "POLICE ACCIDENT REPORT",
                        "layout_tag": "title",
                        "confidence": 0.98,
                        "polygon": [[10, 20], [100, 20], [100, 40], [10, 40]],
                    },
                    {
                        "text": "Traffic signal was RED at 10:14 PM.",
                        "layout_tag": "paragraph",
                        "confidence": 0.96,
                        "polygon": [[10, 50], [250, 50], [250, 70], [10, 70]],
                    },
                    {
                        "text": "Officer Note: handwritten signature",
                        "layout_tag": "handwriting",
                        "confidence": 0.88,
                        "polygon": [[10, 80], [150, 80], [150, 100], [10, 100]],
                    },
                ],
            }
        ]
    }

    pages = _parse_sarvam_vision_result(sample_vision_response)
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["page_number"] == 1
    assert "POLICE ACCIDENT REPORT" in p1["extracted_text"]
    assert "Traffic signal was RED" in p1["extracted_text"]
    assert p1["has_handwriting"] is True
    assert p1["confidence"] > 0.90
    assert len(p1["bounding_boxes"]) == 3
    assert p1["bounding_boxes"][0]["polygon"] == [[10, 20], [100, 20], [100, 40], [10, 40]]


def test_process_with_local_pdf_fallback():
    dummy_text_data = b"State of California v. John Doe\nExhibit A: Incident Report"
    pages = _process_with_local_pdf(dummy_text_data)
    assert len(pages) >= 1
    assert "State of California" in pages[0]["extracted_text"]
