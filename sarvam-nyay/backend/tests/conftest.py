import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-minimum-32-chars-ok!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SYNC_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-mock-key")
os.environ.setdefault("DEEPINFRA_API_KEY", "test-deepinfra-mock-key")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.cognitiveservices.azure.com/")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_KEY", "test-azure-doc-intel-mock-key")
os.environ.setdefault("DEBUG", "true")
"""
VeriDictum AI — Test Configuration & Fixtures
Uses SQLite in-memory for fast, dependency-free tests.
"""

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models import AccountStatus, Organisation, SubscriptionTier, User, UserRole
from app.tasks.celery_app import celery_app
from app.utils.security import create_access_token, hash_password

celery_app.conf.update(task_always_eager=True)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    TestSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_org(db: AsyncSession) -> Organisation:
    org = Organisation(
        name="Test Law Firm",
        subscription_tier=SubscriptionTier.PROFESSIONAL,
    )
    db.add(org)
    await db.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db: AsyncSession, test_org: Organisation) -> User:
    user = User(
        organisation_id=test_org.id,
        email="attorney@testfirm.com",
        hashed_password=hash_password("SecurePass123!"),
        full_name="John Attorney",
        role=UserRole.ATTORNEY,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    token = create_access_token(str(test_user.id), {"role": test_user.role})
    return {"Authorization": f"Bearer {token}"}
