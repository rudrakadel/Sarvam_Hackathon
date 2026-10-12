"""
VeriDictum AI — Application Configuration
Centralised settings loaded from environment variables via pydantic-settings.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "Sarvam Nyaya"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # --- Database ---
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- JWT ---
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # --- OpenAI ---
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4.1-nano-2025-04-14"
    OPENAI_BASE_URL: Optional[str] = None

    # --- Provider Selection ---
    STT_PROVIDER: str = "sarvam"        # "sarvam" | "deepinfra"
    OCR_PROVIDER: str = "sarvam"        # "sarvam" | "local"
    STORAGE_BACKEND: str = "local"      # 100% local filesystem storage

    # --- Sarvam AI (Speech-to-Text, Vision OCR, & AI Summarizer) ---
    SARVAM_API_KEY: str = ""
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_VISION_MODEL: str = "sarvam-vision-v1"
    SARVAM_SUMMARY_MODEL: str = "sarvam-105b"
    SARVAM_LANGUAGE_CODE: str = "en-IN"

    # --- Local File Storage Containers ---
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER_AUDIO: str = "audio"
    AZURE_STORAGE_CONTAINER_DOCUMENTS: str = "documents"
    AZURE_STORAGE_CONTAINER_REPORTS: str = "reports"
    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = ""
    AZURE_DOC_INTELLIGENCE_KEY: str = ""

    # --- Pinecone ---
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = "us-east-1"
    PINECONE_INDEX_NAME: str = "veridictum-vectors"

    # --- Email ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "Sarvam Nyaya <noreply@sarvam.ai>"

    # --- File Size Limits ---
    MAX_AUDIO_SIZE_BYTES: int = 5_368_709_120   # 5 GB
    MAX_DOCUMENT_SIZE_BYTES: int = 524_288_000  # 500 MB

    # JSON / form bodies on non-upload routes — small by default so a malicious
    # client can't pin a worker by streaming a 500 MB JSON document at us.
    MAX_JSON_BODY_BYTES: int = 1_048_576        # 1 MB

    # --- Idempotency ---
    # When an Idempotency-Key header is present on POST/PATCH/PUT/DELETE,
    # the response is cached in Redis for this many seconds so a retried
    # client request returns the original outcome instead of re-running.
    IDEMPOTENCY_TTL_SECONDS: int = 86_400       # 24 hours

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- TOTP ---
    TOTP_ISSUER: str = "Sarvam Nyaya"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()
