"""
VeriDictum AI — Database Engine & Session Management
Async SQLAlchemy setup with connection pooling for production readiness.
"""

import json
import uuid as _uuid_module
from typing import Any, AsyncGenerator

from sqlalchemy import String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.config import settings


# ---------------------------------------------------------------------------
# UUIDString — stores UUID as varchar(36), accepts uuid.UUID or str
# ---------------------------------------------------------------------------
class UUIDString(TypeDecorator):
    """Stores UUIDs as 36-char strings. Compatible with SQLite and PostgreSQL."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, _uuid_module.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return value  # keep as string; callers expect str


# ---------------------------------------------------------------------------
# JSONText — stores dicts/lists as JSON text (SQLite & PostgreSQL compatible)
# ---------------------------------------------------------------------------
class JSONText(TypeDecorator):
    """Stores Python dicts/lists as JSON-encoded text. Works with any DB."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value  # already serialized
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

# ---------------------------------------------------------------------------
# Async engine
# ---------------------------------------------------------------------------
_engine_kwargs = dict(echo=settings.DEBUG, pool_pre_ping=True)
# SQLite does not support pool_size / max_overflow
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Base declarative class shared by all models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency — FastAPI route injection
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session; always closes on exit."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
