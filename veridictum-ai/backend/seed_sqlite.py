#!/usr/bin/env python3
"""
VeriDictum AI — SQLite-compatible minimal seed script
Creates demo org, users, cases, and contradictions.
"""
import asyncio
import os
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./veridictum.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///./veridictum.db"
os.environ.setdefault("SECRET_KEY", "dev-secret-key-minimum-32-chars-ok!")
os.environ.setdefault("OPENAI_API_KEY", "sk-placeholder-not-needed-for-seed")
os.environ.setdefault("DEEPINFRA_API_KEY", "placeholder")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://placeholder.cognitiveservices.azure.com/")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_KEY", "placeholder")

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models import AccountStatus, Organisation, SubscriptionTier, User, UserRole
from app.models.case import Case, CaseStatus, CaseType, CaseMember, CasePermission
from app.models.contradiction import Contradiction, ContradictionSeverity, ContradictionStatus
from app.utils.security import hash_password

DATABASE_URL = os.environ["DATABASE_URL"]
NOW = datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


async def seed(session: AsyncSession) -> None:
    # Check if already seeded
    existing = await session.execute(select(Organisation).limit(1))
    if existing.scalar_one_or_none():
        print("DB already seeded — skipping.")
        return

    # Organisation
    org = Organisation(
        name="Blackwood & Associates",
        subscription_tier=SubscriptionTier.PROFESSIONAL,
    )
    session.add(org)
    await session.flush()

    # Users
    qa_user = User(
        organisation_id=org.id,
        email="qa.tester@gmail.com",
        hashed_password=hash_password("QATest2026!Secure"),
        full_name="QA Tester",
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    admin = User(
        organisation_id=org.id,
        email="admin@blackwoodlaw.com",
        hashed_password=hash_password("Demo@Pass123!"),
        full_name="Sarah Blackwood",
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    attorney1 = User(
        organisation_id=org.id,
        email="m.chen@blackwoodlaw.com",
        hashed_password=hash_password("Demo@Pass123!"),
        full_name="Marcus Chen",
        role=UserRole.ATTORNEY,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    attorney2 = User(
        organisation_id=org.id,
        email="p.rodriguez@blackwoodlaw.com",
        hashed_password=hash_password("Demo@Pass123!"),
        full_name="Patricia Rodriguez",
        role=UserRole.ATTORNEY,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    paralegal = User(
        organisation_id=org.id,
        email="j.okafor@blackwoodlaw.com",
        hashed_password=hash_password("Demo@Pass123!"),
        full_name="James Okafor",
        role=UserRole.PARALEGAL,
        status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    session.add_all([qa_user, admin, attorney1, attorney2, paralegal])
    await session.flush()

    # Cases
    cases_data = [
        {
            "case_number": "2026-CR-004821",
            "title": "State v. Harrison — Corporate Fraud",
            "case_type": CaseType.CRIMINAL,
            "status": CaseStatus.IN_REVIEW,
            "court": "Superior Court of California",
            "jurisdiction": "Los Angeles County, CA",
            "description": "Criminal fraud case involving falsified financial statements and investor deception over a three-year period.",
            "parties": {"defendant": "Derek Harrison", "prosecutor": "Los Angeles County DA"},
            "created_by": admin,
            "days_ago": 145,
        },
        {
            "case_number": "2026-CV-008934",
            "title": "Martinez v. Apex Pharmaceuticals — Employment Dispute",
            "case_type": CaseType.CIVIL,
            "status": CaseStatus.OPEN,
            "court": "U.S. District Court, C.D. Cal.",
            "jurisdiction": "Los Angeles County, CA",
            "description": "Wrongful termination claim alleging retaliation after plaintiff raised safety concerns about drug trial procedures.",
            "parties": {"plaintiff": "Elena Martinez", "defendant": "Apex Pharmaceuticals Inc."},
            "created_by": attorney1,
            "days_ago": 87,
        },
        {
            "case_number": "2026-CR-003156",
            "title": "People v. Nguyen — Homicide Defense",
            "case_type": CaseType.CRIMINAL,
            "status": CaseStatus.OPEN,
            "court": "Los Angeles Superior Court",
            "jurisdiction": "Los Angeles County, CA",
            "description": "First-degree homicide defense. Multiple witnesses have provided conflicting testimony.",
            "parties": {"defendant": "Thomas Nguyen", "prosecutor": "Los Angeles County DA"},
            "created_by": admin,
            "days_ago": 62,
        },
        {
            "case_number": "2026-ARB-000572",
            "title": "Westfield Construction v. City of Pasadena — Contract Arbitration",
            "case_type": CaseType.ARBITRATION,
            "status": CaseStatus.IN_REVIEW,
            "court": "JAMS Arbitration",
            "jurisdiction": "Pasadena, CA",
            "description": "Commercial arbitration over alleged breach of $24M municipal construction contract.",
            "parties": {"claimant": "Westfield Construction LLC", "respondent": "City of Pasadena"},
            "created_by": attorney2,
            "days_ago": 34,
        },
        {
            "case_number": "2026-DEP-001108",
            "title": "Holloway Estate — Deposition Review",
            "case_type": CaseType.DEPOSITION,
            "status": CaseStatus.OPEN,
            "court": "Los Angeles Probate Court",
            "jurisdiction": "Los Angeles County, CA",
            "description": "Estate dispute involving contested will provisions and creditor claims.",
            "parties": {"petitioner": "Holloway Family Trust", "respondent": "Creditor Coalition"},
            "created_by": attorney1,
            "days_ago": 12,
        },
    ]

    case_objs = []
    for cd in cases_data:
        case = Case(
            organisation_id=org.id,
            created_by_id=cd["created_by"].id,
            case_number=cd["case_number"],
            title=cd["title"],
            case_type=cd["case_type"],
            status=cd["status"],
            court=cd["court"],
            jurisdiction=cd["jurisdiction"],
            description=cd["description"],
            parties=cd["parties"],
            created_at=_days_ago(cd["days_ago"]),
            updated_at=_days_ago(max(0, cd["days_ago"] - 5)),
        )
        session.add(case)
        case_objs.append(case)
    await session.flush()

    # Add qa_user as member of first case
    result = await session.execute(
        select(Case).where(Case.case_number == "2026-CR-004821")
    )
    case1 = result.scalar_one()

    qa_member = CaseMember(
        case_id=case1.id,
        user_id=qa_user.id,
        permission=CasePermission.CASE_OWNER,
        granted_by_id=admin.id,
    )
    session.add(qa_member)

    # Contradictions for case1
    contradictions = [
        Contradiction(
            case_id=case1.id,
            severity=ContradictionSeverity.CRITICAL,
            status=ContradictionStatus.AI_SUGGESTED,
            confidence_score=0.97,
            contradiction_type="temporal",
            transcript_text="I was in New York the entire week of March 12th. I never signed any documents in California during that period.",
            transcript_speaker="Derek Harrison",
            transcript_timestamp_start=134.0,
            document_text="Signature verification confirms D. Harrison signed the Q1 2025 financial amendment in the Los Angeles office on March 14, 2025 at 2:47 PM.",
            document_page=3,
            explanation="Critical temporal contradiction: Harrison claims he was in New York, but the document confirms his signature was obtained in Los Angeles.",
        ),
        Contradiction(
            case_id=case1.id,
            severity=ContradictionSeverity.HIGH,
            status=ContradictionStatus.CONFIRMED,
            confidence_score=0.91,
            attorney_notes="Confirmed by Marcus Chen on 2026-04-15. Travel records requested from American Airlines.",
            contradiction_type="factual",
            transcript_text="The board was fully informed about the projected revenue figures before they approved the Q1 amendment.",
            transcript_speaker="Derek Harrison",
            transcript_timestamp_start=287.5,
            document_text="Board minutes dated March 10, 2025 indicate the amendment was approved without Q1 revenue projections.",
            document_page=7,
            explanation="High-severity factual contradiction: Harrison claims the board was informed, but minutes show revenue projections were not available.",
        ),
        Contradiction(
            case_id=case1.id,
            severity=ContradictionSeverity.HIGH,
            status=ContradictionStatus.AI_SUGGESTED,
            confidence_score=0.88,
            contradiction_type="factual",
            transcript_text="I never personally reviewed investor communications. That was entirely handled by our IR team.",
            transcript_speaker="Derek Harrison",
            transcript_timestamp_start=412.0,
            document_text="Email chain from March 2025 shows D. Harrison as direct sender of investor update emails.",
            document_page=12,
            explanation="Factual contradiction regarding personal involvement: Harrison denies reviewing investor communications.",
        ),
    ]
    session.add_all(contradictions)
    await session.flush()

    print("Seed data created successfully.")
    print(f"  Organisation: {org.name}")
    print(f"  QA user: qa.tester@gmail.com / QATest2026!Secure")
    print(f"  Admin: admin@blackwoodlaw.com / Demo@Pass123!")
    print(f"  Cases seeded: {len(cases_data)}")
    print(f"  Contradictions seeded: {len(contradictions)}")


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        async with session.begin():
            await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
