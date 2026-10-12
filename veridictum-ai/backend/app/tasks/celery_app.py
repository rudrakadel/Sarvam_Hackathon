"""
VeriDictum AI — Celery Application Configuration
Async task queue for transcription, OCR, and contradiction analysis.
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "veridictum",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.transcription",
        "app.tasks.ocr",
        "app.tasks.contradiction",
        "app.tasks.report",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_max_retries=3,
    task_default_retry_delay=30,
    result_expires=86400,      # Results expire after 24 hours
    task_routes={
        "app.tasks.transcription.*": {"queue": "transcription"},
        "app.tasks.ocr.*": {"queue": "ocr"},
        "app.tasks.contradiction.*": {"queue": "analysis"},
        "app.tasks.report.*": {"queue": "reports"},
    },
)
