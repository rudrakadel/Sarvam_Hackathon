#!/usr/bin/env python3
"""
VeriDictum AI — Screenshot-Ready Demo Seeder

Re-creates the dataset implied by the marketing-grade screenshots: one persona
("Sarah Blackwood"), 15 topical cases with **unique** evidence per case, real
seeded contradictions on the lead case so the Contradictions tab is populated,
and a mix of COMPLETE / GENERATING / QUEUED reports so the Reports page tells a
story.

Why this exists:
- The previous `seed_sqlite.py` seeded only 5 cases and never connected the
  contradictions to transcripts or documents, so the AI Case Summary tile and
  the Contradictions tab rendered inconsistent data.
- The Phase-B/C screenshot driver created 15 cases via API but the contradiction
  insertion phase silently failed (transcripts.audio_file_id NOT NULL
  constraint), leaving the Contradictions tab empty across all cases while the
  case-stats endpoint still showed CRITICAL counts from a prior run.

Usage:
    cd backend && python seed_screenshots.py
    # default DB: SQLite at ./veridictum.db
    # override with: DATABASE_URL=postgresql+asyncpg://... python seed_screenshots.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# ── env bootstrap — must be set before importing app modules ─────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./veridictum.db")
os.environ.setdefault("SYNC_DATABASE_URL", "sqlite:///./veridictum.db")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-minimum-32-chars-ok!")
os.environ.setdefault("OPENAI_API_KEY", "sk-placeholder-not-needed-for-seed")
os.environ.setdefault("DEEPINFRA_API_KEY", "placeholder")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://placeholder.cognitiveservices.azure.com/")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_KEY", "placeholder")

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models import (
    AccountStatus,
    AnalysisJob,
    AudioFile,
    Case,
    CaseMember,
    CasePermission,
    CaseStatus,
    CaseType,
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    Document,
    DocumentPage,
    NLQuery,
    Organisation,
    ProcessingStatus,
    Report,
    ReportStatus,
    SubscriptionTier,
    Transcript,
    User,
    UserRole,
)
from app.utils.security import hash_password

DATABASE_URL = os.environ["DATABASE_URL"]
NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


# ────────────────────────────────────────────────────────────────────────────
# CASE BLUEPRINTS — every case has topically-unique evidence
# ────────────────────────────────────────────────────────────────────────────
#
# Each entry is consumed by `seed_case_evidence`. The first entry is the LEAD
# case (Whitfield); the lead case gets full seeded contradictions so the
# Contradictions tab and the AI Case Summary tile are consistent.

CASE_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "case_number": "2026-CR-00142",
        "title": "People v. Marcus Whitfield",
        "case_type": CaseType.CRIMINAL,
        "status": CaseStatus.OPEN,
        "court": "Los Angeles Superior Court — Dept 102",
        "jurisdiction": "California",
        "description": "Aggravated assault. Defendant denies presence at the scene; security log, witness audio, and CCTV imply otherwise.",
        "parties": {"plaintiff": "The People of California", "defendant": "Marcus Whitfield"},
        "tags": ["criminal", "assault", "felony"],
        "days_ago": 12,
        "audio": [
            ("Whitfield_TrialDay1.wav", 4.2 * 1024 * 1024, 5 * 60.0),
            ("Witness_A_DirectExamination.wav", 6.3 * 1024 * 1024, 7 * 60.0),
            ("Whitfield_CrossExam_Day2.wav", 11.6 * 1024 * 1024, 13 * 60.0),
            ("911_Call_2026-04-12.wav", 1.7 * 1024 * 1024, 2 * 60.0),
        ],
        "documents": [
            ("LAPD_Incident_Report_8847.pdf", 312_000, 8, 0.97),
            ("Building_Badge_Log_April_2026.pdf", 184_000, 3, 0.99),
        ],
        "contradictions": [
            {
                "severity": ContradictionSeverity.CRITICAL,
                "status": ContradictionStatus.AI_SUGGESTED,
                "confidence": 0.94,
                "type": "temporal",
                "transcript_text": "I was home the entire evening of April 11th. I never left the apartment after 8 PM.",
                "transcript_speaker": "Marcus Whitfield",
                "transcript_t_start": 134.0,
                "document_text": "Building badge log shows Marcus Whitfield (ID #4471) badge-out at 11:08 PM and re-entry at 02:41 AM on the night of April 11–12, 2026.",
                "document_page": 3,
                "explanation": "Critical temporal contradiction: Defendant claims he was home from 20:00 onward on April 11th, but the building badge log captures him badging out at 23:08 and not returning until 02:41 the next morning — a 3-hour 33-minute window that overlaps the incident.",
            },
            {
                "severity": ContradictionSeverity.HIGH,
                "status": ContradictionStatus.AI_SUGGESTED,
                "confidence": 0.88,
                "type": "factual",
                "transcript_text": "I never personally spoke to Mr. Reyes that night. I have not had contact with him in months.",
                "transcript_speaker": "Marcus Whitfield",
                "transcript_t_start": 287.5,
                "document_text": "Police incident report logs a 911 call from defendant's registered phone number to dispatch at 23:54, with the caller identifying himself by name and asking about Mr. Reyes by first name.",
                "document_page": 5,
                "explanation": "Factual contradiction: Defendant denies any contact with the alleged victim that night, but a 911 call from his registered phone places him in conversation referencing the victim by first name 46 minutes before the alleged incident.",
            },
            {
                "severity": ContradictionSeverity.HIGH,
                "status": ContradictionStatus.CONFIRMED,
                "confidence": 0.91,
                "type": "identity",
                "transcript_text": "Witness A is mistaken — she's never met me and could not pick me out of a crowd.",
                "transcript_speaker": "Marcus Whitfield",
                "transcript_t_start": 412.0,
                "document_text": "LAPD line-up worksheet dated April 13 records Witness A identifying defendant (position #4) within 8 seconds, with no examiner prompting (verified on body-cam recording).",
                "document_page": 7,
                "explanation": "Identity contradiction: Defendant claims Witness A has never seen him, but a same-week LAPD line-up shows the witness identifying him without hesitation. Body-cam corroboration available.",
                "attorney_notes": "Confirmed during attorney review on 2026-05-18. Line-up procedure was double-blind; identification holds.",
            },
        ],
        "nl_queries": [
            (
                "What inconsistencies appear between Defendant Whitfield's alibi and the building badge log?",
                "Three material contradictions surface: (1) Whitfield states he was home the entire evening, but the badge log places him outside the building from 23:08 to 02:41. (2) He denies contact with Mr. Reyes that night, yet a 911 call from his registered phone references the victim by name at 23:54. (3) He claims Witness A has never met him, but a same-week LAPD line-up has the witness identifying him in 8 seconds. Citation strength: badge log (Doc p. 3, page-level OCR conf 0.99), incident report 911 call entry (Doc p. 5), line-up worksheet (Doc p. 7).",
                2.4,
                [
                    {"source_type": "transcript", "speaker": "Marcus Whitfield", "timestamp": 134.0},
                    {"source_type": "document", "page": 3},
                    {"source_type": "document", "page": 5},
                    {"source_type": "document", "page": 7},
                ],
            ),
            (
                "Did the defendant ever directly admit to walking by the location of the assault?",
                "Direct admission is absent in the transcripts indexed so far. The closest signal is a hedge during cross-examination (Whitfield_CrossExam_Day2 at 17:08) where Whitfield says 'I might have walked by Main Street but I don't recall.' Counsel may want to probe this further; ambiguity is high. No direct geo-evidence in this corpus.",
                1.8,
                [
                    {"source_type": "document", "page": 5},
                ],
            ),
        ],
    },
    {
        "case_number": "2026-CV-00891",
        "title": "Marin v. Helix Pharmaceuticals",
        "case_type": CaseType.CIVIL,
        "status": CaseStatus.OPEN,
        "court": "Northern District of California",
        "jurisdiction": "Federal — 9th Circuit",
        "description": "Wrongful-death claim alleging concealed adverse-event data in a Phase II oncology trial.",
        "parties": {"plaintiff": "Estate of Carlos Marin", "defendant": "Helix Pharmaceuticals Inc"},
        "tags": ["civil", "wrongful_death", "pharmaceuticals", "class_action_candidate"],
        "days_ago": 9,
        "audio": [
            ("MarinDepo_2026-04-08.wav", 5.2 * 1024 * 1024, 10 * 60.0),
            ("Dr_Kapoor_ExpertOpinion.wav", 18.9 * 1024 * 1024, 21 * 60.0),
            ("ComplianceOfficer_Statement.wav", 6.3 * 1024 * 1024, 7 * 60.0),
        ],
        "documents": [
            ("Helix_Pharma_Trial_Protocol_v3.pdf", 612_000, 24, 0.95),
            ("FDA_AdverseEventReport_NDA77321.pdf", 198_000, 11, 0.98),
        ],
        "contradictions": [
            {
                "severity": ContradictionSeverity.CRITICAL,
                "status": ContradictionStatus.AI_SUGGESTED,
                "confidence": 0.92,
                "type": "factual",
                "transcript_text": "We disclosed every Grade-3 adverse event to the FDA on a rolling basis. There was no batch holdback.",
                "transcript_speaker": "Compliance Officer (Helix)",
                "transcript_t_start": 95.0,
                "document_text": "FDA NDA adverse-event report 77321 shows 4 Grade-3 events first disclosed in a batch filing 41 days after individual occurrence, exceeding the 15-day individual disclosure obligation under 21 CFR 314.80.",
                "document_page": 4,
                "explanation": "Critical regulatory contradiction: the witness denies batch holdback of adverse-event disclosures, but the FDA filing record shows a 41-day delay on four Grade-3 events.",
            },
        ],
        "nl_queries": [],
    },
    {
        "case_number": "2026-AR-00045",
        "title": "MedTech Robotics v. Apex Surgical",
        "case_type": CaseType.ARBITRATION,
        "status": CaseStatus.IN_REVIEW,
        "court": "JAMS Arbitration — San Francisco",
        "jurisdiction": "California — JAMS Rules",
        "description": "IP dispute over surgical-robot patent claims after termination of joint-development agreement.",
        "parties": {"claimant": "MedTech Robotics LLC", "respondent": "Apex Surgical Inc"},
        "tags": ["arbitration", "contract", "ip"],
        "days_ago": 28,
        "audio": [
            ("MedTechApex_PreHearing_2026-04-22.wav", 9.4 * 1024 * 1024, 12 * 60.0),
            ("JointDev_PhaseGate_RecordedCall.wav", 14.1 * 1024 * 1024, 18 * 60.0),
        ],
        "documents": [
            ("JointDevelopment_Agreement_2024.pdf", 412_000, 31, 0.96),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-CR-00203",
        "title": "United States v. Devin Park",
        "case_type": CaseType.CRIMINAL,
        "status": CaseStatus.OPEN,
        "court": "Eastern District of New York",
        "jurisdiction": "Federal — 2nd Circuit",
        "description": "White-collar securities fraud — alleged spoofing across two trading desks in Q4 2025.",
        "parties": {"plaintiff": "United States of America", "defendant": "Devin Park"},
        "tags": ["criminal", "white_collar", "federal"],
        "days_ago": 41,
        "audio": [
            ("Park_GrandJury_Excerpt.wav", 7.8 * 1024 * 1024, 9 * 60.0),
        ],
        "documents": [
            ("SEC_Trading_Log_Q4_2025.pdf", 891_000, 47, 0.99),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-CV-01124",
        "title": "Tate v. Riverside Construction",
        "case_type": CaseType.CIVIL,
        "status": CaseStatus.OPEN,
        "court": "Cook County Circuit Court — Law Division",
        "jurisdiction": "Illinois",
        "description": "Premises-liability injury from scaffold collapse at a downtown jobsite.",
        "parties": {"plaintiff": "Linda Tate", "defendant": "Riverside Construction LLC"},
        "tags": ["civil", "personal_injury", "premises_liability"],
        "days_ago": 67,
        "audio": [
            ("Tate_Deposition_2026-03-14.wav", 12.5 * 1024 * 1024, 16 * 60.0),
            ("Site_Foreman_Interview.wav", 4.4 * 1024 * 1024, 6 * 60.0),
        ],
        "documents": [
            ("OSHA_Inspection_Report_2026-03-10.pdf", 224_000, 14, 0.94),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-HR-00078",
        "title": "In re: Custody of A.B.",
        "case_type": CaseType.HEARING,
        "status": CaseStatus.OPEN,
        "court": "Cook County Domestic Relations Division",
        "jurisdiction": "Illinois — Family Court",
        "description": "Custody hearing — contested decision-making and parenting time, minor child (initials only).",
        "parties": {"petitioner": "Sarah Brennan", "respondent": "Michael Brennan"},
        "tags": ["family", "custody", "minor"],
        "days_ago": 6,
        "audio": [
            ("Brennan_GuardianAdLitem_Interview.wav", 8.1 * 1024 * 1024, 11 * 60.0),
        ],
        "documents": [],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-DEP-00033",
        "title": "Quigley v. Aurora Health Network — Deposition",
        "case_type": CaseType.DEPOSITION,
        "status": CaseStatus.OPEN,
        "court": "King County Superior Court",
        "jurisdiction": "Washington",
        "description": "Medical malpractice deposition — physician failed to order CT before discharge.",
        "parties": {"plaintiff": "Patricia Quigley", "defendant": "Aurora Health Network"},
        "tags": ["deposition", "medical_malpractice"],
        "days_ago": 18,
        "audio": [
            ("Quigley_PhysicianDepo.wav", 5.9 * 1024 * 1024, 8 * 60.0),
            ("ChartReview_NurseDeposition.wav", 7.7 * 1024 * 1024, 10 * 60.0),
        ],
        "documents": [
            ("Aurora_DischargeProtocol_2023.pdf", 144_000, 6, 0.97),
        ],
        "contradictions": [
            {
                "severity": ContradictionSeverity.HIGH,
                "status": ContradictionStatus.AI_SUGGESTED,
                "confidence": 0.86,
                "type": "factual",
                "transcript_text": "My standard protocol always includes a CT before discharge for any head-injury presentation.",
                "transcript_speaker": "Dr. Aurora",
                "transcript_t_start": 754.0,
                "document_text": "Quigley discharge summary shows no CT order; chart entries from the attending nurse note discharge was approved verbally without imaging.",
                "document_page": 1,
                "explanation": "Direct contradiction. Dr. Aurora states 'my standard protocol always includes a CT before discharge' (Audio Quigley_PhysicianDepo, 12:34), but the medical records show Ms. Quigley was discharged the same day without imaging. The protocol claim is not supported by the contemporaneous chart entries.",
            },
        ],
        "nl_queries": [
            (
                "Does the physician's deposition contradict the medical records on imaging protocol?",
                "Direct contradiction. Dr. Aurora states 'my standard protocol always includes a CT before discharge' (Audio Quigley_PhysicianDepo, 12:34), but the medical records show Ms. Quigley was discharged the same day without imaging. The protocol claim is not supported by the contemporaneous chart entries. Strength: high. Suggested follow-up: subpoena the hospital's protocol attestation forms for the relevant period.",
                2.3,
                [
                    {"source_type": "document", "page": 1},
                    {"source_type": "transcript", "speaker": "Dr. Aurora", "timestamp": 754.0},
                ],
            ),
        ],
    },
    {
        "case_number": "2026-CV-01512",
        "title": "Greenfield v. Bayline Investments",
        "case_type": CaseType.CIVIL,
        "status": CaseStatus.OPEN,
        "court": "Delaware Court of Chancery",
        "jurisdiction": "Delaware",
        "description": "Breach of fiduciary duty — alleged self-dealing in a LP capital-call cycle.",
        "parties": {"plaintiff": "Greenfield Partners LP", "defendant": "Bayline Investments Inc"},
        "tags": ["civil", "securities", "fiduciary_duty"],
        "days_ago": 22,
        "audio": [
            ("Bayline_GP_Recorded_Update_Call.wav", 16.2 * 1024 * 1024, 22 * 60.0),
        ],
        "documents": [
            ("LP_Agreement_2021_Bayline_FundII.pdf", 482_000, 38, 0.96),
            ("Capital_Call_Notice_Q3.pdf", 92_000, 4, 0.99),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-CR-00345",
        "title": "State v. Ophelia Reyes",
        "case_type": CaseType.CRIMINAL,
        "status": CaseStatus.OPEN,
        "court": "Travis County District Court",
        "jurisdiction": "Texas",
        "description": "Drug-possession charges with disputed evidence chain.",
        "parties": {"plaintiff": "State of Texas", "defendant": "Ophelia Reyes"},
        "tags": ["criminal", "drug_crime"],
        "days_ago": 31,
        "audio": [
            ("Reyes_TrafficStop_Bodycam_Audio.wav", 3.1 * 1024 * 1024, 4 * 60.0),
        ],
        "documents": [
            ("EvidenceCustody_Log_Reyes.pdf", 56_000, 2, 0.98),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-AR-00091",
        "title": "Polaris Logistics v. NorthStar Freight",
        "case_type": CaseType.ARBITRATION,
        "status": CaseStatus.OPEN,
        "court": "ICC International Court of Arbitration",
        "jurisdiction": "International — ICC",
        "description": "International freight contract dispute — delayed-delivery damages.",
        "parties": {"claimant": "Polaris Logistics SA", "respondent": "NorthStar Freight Corp"},
        "tags": ["arbitration", "international", "contract"],
        "days_ago": 51,
        "audio": [
            ("Polaris_NorthStar_Hearing_Day1.wav", 22.3 * 1024 * 1024, 28 * 60.0),
        ],
        "documents": [],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-HR-00114",
        "title": "In re: Probate of Estate of D. Holloway",
        "case_type": CaseType.HEARING,
        "status": CaseStatus.OPEN,
        "court": "Surrogate's Court — New York County",
        "jurisdiction": "New York",
        "description": "Will-contest hearing; multiple holographic codicils submitted.",
        "parties": {"petitioner": "Executor — Anne Holloway"},
        "tags": ["probate", "estate", "contested_will"],
        "days_ago": 36,
        "audio": [
            ("Holloway_Executor_Statement.wav", 3.9 * 1024 * 1024, 5 * 60.0),
        ],
        "documents": [
            ("Holloway_Will_Codicil_2.pdf", 38_000, 2, 0.92),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-CV-01876",
        "title": "Doe v. NorCal University",
        "case_type": CaseType.CIVIL,
        "status": CaseStatus.OPEN,
        "court": "Alameda County Superior Court",
        "jurisdiction": "California",
        "description": "Title-IX civil action — alleged due-process failures in disciplinary hearing.",
        "parties": {"plaintiff": "Jane Doe (under seal)", "defendant": "NorCal University"},
        "tags": ["civil", "title_ix", "education"],
        "days_ago": 14,
        "audio": [],
        "documents": [
            ("NorCal_Disciplinary_Hearing_Record_REDACTED.pdf", 308_000, 22, 0.93),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-DEP-00075",
        "title": "Maxwell v. Greenway Logistics — Driver Deposition",
        "case_type": CaseType.DEPOSITION,
        "status": CaseStatus.IN_REVIEW,
        "court": "Miami-Dade Circuit Court",
        "jurisdiction": "Florida",
        "description": "Commercial-vehicle collision — disputed log-book and rest-break compliance.",
        "parties": {"plaintiff": "Eleanor Maxwell", "defendant": "Greenway Logistics LLC"},
        "tags": ["deposition", "commercial_vehicle", "personal_injury"],
        "days_ago": 24,
        "audio": [
            ("Maxwell_DriverDeposition.wav", 8.6 * 1024 * 1024, 11 * 60.0),
            ("DispatchLog_Voice_Recording.wav", 2.2 * 1024 * 1024, 3 * 60.0),
        ],
        "documents": [
            ("FMCSA_HoursOfService_Log_Driver_Maxwell.pdf", 178_000, 9, 0.95),
        ],
        "contradictions": [
            {
                "severity": ContradictionSeverity.MEDIUM,
                "status": ContradictionStatus.AI_SUGGESTED,
                "confidence": 0.79,
                "type": "temporal",
                "transcript_text": "I took my mandatory 30-minute break at 11:00 AM that morning, exactly as the log shows.",
                "transcript_speaker": "Driver Maxwell",
                "transcript_t_start": 318.0,
                "document_text": "FMCSA HoS log entry for that date records no mandatory break between 09:00 and 14:00; the auto-recorded ELD pings show continuous driving over that interval.",
                "document_page": 4,
                "explanation": "Medium-severity temporal contradiction between deposition testimony and the ELD log. ELD entries are auto-generated and harder to dispute than the witness recollection.",
            },
        ],
        "nl_queries": [],
    },
    {
        "case_number": "2026-OTH-00012",
        "title": "In re: Sealed Grand Jury Matter 2026-04",
        "case_type": CaseType.OTHER,
        "status": CaseStatus.OPEN,
        "court": "United States District Court — DDC",
        "jurisdiction": "Federal — DC Circuit",
        "description": "Sealed — federal grand-jury subpoena response and document-production motion.",
        "parties": {"matter": "Sealed — Federal Grand Jury Subpoena"},
        "tags": ["sealed", "federal", "grand_jury"],
        "days_ago": 4,
        "audio": [],
        "documents": [
            ("Subpoena_DDC_Sealed_2026-04.pdf", 24_000, 2, 0.99),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
    {
        "case_number": "2026-HR-00198",
        "title": "Patel v. Atlas Holdings — Trademark Infringement",
        "case_type": CaseType.HEARING,
        "status": CaseStatus.OPEN,
        "court": "USPTO TTAB Hearing",
        "jurisdiction": "Federal — USPTO",
        "description": "TTAB opposition proceeding — likelihood of confusion in software trademarks.",
        "parties": {"petitioner": "Patel Industries", "respondent": "Atlas Holdings Inc"},
        "tags": ["hearing", "ip", "trademark"],
        "days_ago": 16,
        "audio": [],
        "documents": [
            ("TTAB_Notice_of_Opposition_Patel_v_Atlas.pdf", 88_000, 6, 0.97),
        ],
        "contradictions": [],
        "nl_queries": [],
    },
]


# Reports — a mix of statuses so the global Reports page actually communicates
# a workflow rather than 10 in-progress spinners. Each entry references a case
# by index in CASE_BLUEPRINTS so we don't have to know IDs ahead of time.
REPORT_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "case_idx": 0,
        "title": "Whitfield — Full Trial Summary Report",
        "report_type": "FULL_SUMMARY",
        "format": "PDF",
        "status": ReportStatus.COMPLETE,
        "page_count": 18,
        "minutes_ago": 35,
    },
    {
        "case_idx": 6,  # Quigley
        "title": "Quigley v. Aurora Health — Physician Testimony Analysis",
        "report_type": "FULL_SUMMARY",
        "format": "PDF",
        "status": ReportStatus.COMPLETE,
        "page_count": 14,
        "minutes_ago": 92,
    },
    {
        "case_idx": 0,
        "title": "Whitfield — Contradiction Intelligence Brief",
        "report_type": "CONTRADICTIONS",
        "format": "PDF",
        "status": ReportStatus.GENERATING,
        "minutes_ago": 4,
    },
    {
        "case_idx": 1,  # Marin
        "title": "Marin v. Helix — Contradiction Report",
        "report_type": "CONTRADICTIONS",
        "format": "DOCX",
        "status": ReportStatus.QUEUED,
        "minutes_ago": 2,
    },
    {
        "case_idx": 7,  # Greenfield
        "title": "Greenfield v. Bayline — Discovery Summary",
        "report_type": "FULL_SUMMARY",
        "format": "PDF",
        "status": ReportStatus.QUEUED,
        "minutes_ago": 12,
    },
    {
        "case_idx": 12,  # Maxwell
        "title": "Maxwell — Driver Deposition Inconsistencies",
        "report_type": "CONTRADICTIONS",
        "format": "PDF",
        "status": ReportStatus.GENERATING,
        "minutes_ago": 6,
    },
]


# ────────────────────────────────────────────────────────────────────────────
# Seed routine
# ────────────────────────────────────────────────────────────────────────────


async def seed(session: AsyncSession, *, fresh: bool = False) -> None:
    """Populate the DB. Use `fresh=True` to nuke existing case data first."""

    if fresh:
        # Remove anything tied to our demo organisation before re-seeding.
        # We delete in FK-safe order. Use a sub-select for the org id.
        org_rows = await session.execute(
            select(Organisation).where(Organisation.name == "Blackwood & Associates")
        )
        org_row = org_rows.scalar_one_or_none()
        if org_row:
            await session.execute(delete(NLQuery).where(NLQuery.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(Contradiction).where(Contradiction.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(AnalysisJob).where(AnalysisJob.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(Report).where(Report.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(DocumentPage).where(DocumentPage.document_id.in_(
                select(Document.id).join(Case, Document.case_id == Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(Document).where(Document.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(Transcript).where(Transcript.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(AudioFile).where(AudioFile.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(CaseMember).where(CaseMember.case_id.in_(
                select(Case.id).where(Case.organisation_id == org_row.id)
            )))
            await session.execute(delete(Case).where(Case.organisation_id == org_row.id))
            await session.flush()

    # ── Organisation ──
    org_row = (await session.execute(
        select(Organisation).where(Organisation.name == "Blackwood & Associates")
    )).scalar_one_or_none()
    if not org_row:
        org_row = Organisation(
            name="Blackwood & Associates",
            subscription_tier=SubscriptionTier.PROFESSIONAL,
        )
        session.add(org_row)
        await session.flush()

    # ── Users ──
    # Single marketing persona for screenshots. The QA tester is preserved for
    # the existing walkthrough script.
    user_rows = await session.execute(
        select(User).where(User.organisation_id == org_row.id)
    )
    existing_emails = {u.email for u in user_rows.scalars()}

    persona = None
    qa_user = None
    for u in (await session.execute(
        select(User).where(User.organisation_id == org_row.id)
    )).scalars():
        if u.email == "admin@blackwoodlaw.com":
            persona = u
        elif u.email == "qa.tester@gmail.com":
            qa_user = u

    if persona is None:
        persona = User(
            organisation_id=org_row.id,
            email="admin@blackwoodlaw.com",
            hashed_password=hash_password("Demo@Pass123!"),
            full_name="Sarah Blackwood",
            role=UserRole.ADMIN,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        session.add(persona)
        await session.flush()
    elif persona.full_name != "Sarah Blackwood":
        # Lock the persona name on every re-seed so screenshots stay coherent.
        persona.full_name = "Sarah Blackwood"

    if qa_user is None and "qa.tester@gmail.com" not in existing_emails:
        qa_user = User(
            organisation_id=org_row.id,
            email="qa.tester@gmail.com",
            hashed_password=hash_password("QATest2026!Secure"),
            full_name="Sarah Blackwood",  # share the persona name so walkthrough screens stay coherent
            role=UserRole.ADMIN,
            status=AccountStatus.ACTIVE,
            email_verified=True,
        )
        session.add(qa_user)
        await session.flush()
    elif qa_user is not None:
        qa_user.full_name = "Sarah Blackwood"

    # ── Cases (and their evidence) ──
    seeded_cases: list[Case] = []
    for blueprint in CASE_BLUEPRINTS:
        existing = (await session.execute(
            select(Case).where(
                Case.organisation_id == org_row.id,
                Case.case_number == blueprint["case_number"],
            )
        )).scalar_one_or_none()

        if existing is not None:
            seeded_cases.append(existing)
            continue

        kase = Case(
            organisation_id=org_row.id,
            created_by_id=persona.id,
            case_number=blueprint["case_number"],
            title=blueprint["title"],
            case_type=blueprint["case_type"],
            status=blueprint["status"],
            court=blueprint["court"],
            jurisdiction=blueprint["jurisdiction"],
            description=blueprint["description"],
            parties=blueprint["parties"],
            tags=blueprint["tags"],
            created_at=days_ago(blueprint["days_ago"]),
            updated_at=days_ago(max(0, blueprint["days_ago"] - 1)),
        )
        session.add(kase)
        await session.flush()
        seeded_cases.append(kase)

        # Audio files — each gets a Transcript so /audio/{id}/transcripts,
        # /voice-records, and the courtroom audit have content to render.
        # Without the Transcript row, the Phase E voice-records endpoint
        # returns an empty array even though the AudioFile says COMPLETE.
        for filename, size_bytes, duration_s in blueprint["audio"]:
            af = AudioFile(
                case_id=kase.id,
                uploaded_by_id=persona.id,
                original_filename=filename,
                blob_path=f"local-demo/{kase.case_number}/{filename}",
                file_size_bytes=int(size_bytes),
                duration_seconds=duration_s,
                format=filename.rsplit(".", 1)[-1].lower(),
                sha256_hash=f"demo-{kase.case_number}-{filename}",
                mime_type="audio/wav",
                status=ProcessingStatus.COMPLETE,
                language_hint="en",
                processing_completed_at=days_ago(blueprint["days_ago"] - 1),
            )
            session.add(af)
            await session.flush()  # need af.id for the FK

            # Synthetic transcript text. Real Whisper output would be paragraphs
            # of speaker-attributed dialogue; this is just enough to populate
            # the UI panels and let the FTS index do something.
            speaker_a = blueprint["parties"].get("defendant") or blueprint["parties"].get("plaintiff") or "SPEAKER 1"
            speaker_b = blueprint["parties"].get("plaintiff") or blueprint["parties"].get("respondent") or "SPEAKER 2"
            transcript_text = (
                f"[{speaker_a}] This is the demo transcript for {filename}. "
                f"In a real deployment the Whisper Large v3 pipeline would write the diarized "
                f"audio segments here, attributed to each speaker with timestamps.\n"
                f"[{speaker_b}] The transcript powers the AI contradiction engine and Vera's "
                f"natural-language Q&A — every citation Vera emits points back to a transcript "
                f"timestamp or a document page number.\n"
                f"[{speaker_a}] This deposition recording is approximately "
                f"{int(duration_s / 60)} minutes long and indexed for full-text search."
            )
            t = Transcript(
                audio_file_id=af.id,
                case_id=kase.id,
                version=1,
                status=ProcessingStatus.COMPLETE,
                full_text=transcript_text,
                word_count=len(transcript_text.split()),
                segments=[
                    {"speaker": "SPEAKER_00", "start": 0.0, "end": duration_s / 3,
                     "text": transcript_text.split("\n")[0]},
                    {"speaker": "SPEAKER_01", "start": duration_s / 3, "end": 2 * duration_s / 3,
                     "text": transcript_text.split("\n")[1] if "\n" in transcript_text else ""},
                    {"speaker": "SPEAKER_00", "start": 2 * duration_s / 3, "end": duration_s,
                     "text": transcript_text.split("\n")[-1]},
                ],
                speaker_labels={"SPEAKER_00": speaker_a, "SPEAKER_01": speaker_b},
                speaker_count=2,
                whisper_wer_estimate=0.07,
                diarization_der=0.12,
                is_indexed=True,
            )
            session.add(t)

        # Documents
        for filename, size_bytes, page_count, conf in blueprint["documents"]:
            doc = Document(
                case_id=kase.id,
                uploaded_by_id=persona.id,
                original_filename=filename,
                blob_path=f"local-demo/{kase.case_number}/{filename}",
                file_size_bytes=int(size_bytes),
                format=filename.rsplit(".", 1)[-1].lower(),
                sha256_hash=f"demo-{kase.case_number}-{filename}",
                mime_type="application/pdf",
                document_type="evidence",
                page_count=page_count,
                status=ProcessingStatus.COMPLETE,
                avg_confidence=conf,
            )
            session.add(doc)
            await session.flush()
            # one DocumentPage so the page count is non-cosmetic
            for i in range(1, min(page_count, 3) + 1):
                session.add(DocumentPage(
                    document_id=doc.id,
                    page_number=i,
                    extracted_text=f"[seeded] OCR text for page {i} of {filename}",
                    confidence=conf,
                ))

        # Contradictions
        for cdata in blueprint["contradictions"]:
            session.add(Contradiction(
                case_id=kase.id,
                severity=cdata["severity"],
                status=cdata["status"],
                confidence_score=cdata["confidence"],
                contradiction_type=cdata["type"],
                transcript_text=cdata["transcript_text"],
                transcript_speaker=cdata["transcript_speaker"],
                transcript_timestamp_start=cdata["transcript_t_start"],
                document_text=cdata["document_text"],
                document_page=cdata["document_page"],
                explanation=cdata["explanation"],
                reviewed_by_id=persona.id if cdata["status"] == ContradictionStatus.CONFIRMED else None,
                reviewed_at=days_ago(2) if cdata["status"] == ContradictionStatus.CONFIRMED else None,
                attorney_notes=cdata.get("attorney_notes"),
            ))

        # NLQuery history — drives the Ask AI page intro pane
        for query_text, answer_text, secs, citations in blueprint["nl_queries"]:
            session.add(NLQuery(
                case_id=kase.id,
                user_id=persona.id,
                query_text=query_text,
                answer_text=answer_text,
                citations=citations,
                tokens_used=int(secs * 700),
                response_time_ms=int(secs * 1000),
                model_used="gpt-4.1-nano",
            ))

    await session.flush()

    # ── Reports ──
    for rb in REPORT_BLUEPRINTS:
        kase = seeded_cases[rb["case_idx"]]
        existing_rep = (await session.execute(
            select(Report).where(
                Report.case_id == kase.id,
                Report.title == rb["title"],
            )
        )).scalar_one_or_none()
        if existing_rep is not None:
            continue
        created = NOW - timedelta(minutes=rb["minutes_ago"])
        completed_at = (
            NOW - timedelta(minutes=max(rb["minutes_ago"] - 2, 0))
            if rb["status"] == ReportStatus.COMPLETE
            else None
        )
        download_url = None
        if rb["status"] == ReportStatus.COMPLETE:
            download_url = f"https://demo.veridictum.ai/reports/{kase.case_number}-{rb['report_type'].lower()}.{rb['format'].lower()}"
        session.add(Report(
            case_id=kase.id,
            generated_by_id=persona.id,
            title=rb["title"],
            report_type=rb["report_type"],
            format=rb["format"],
            status=rb["status"],
            page_count=rb.get("page_count"),
            download_url=download_url,
            include_contradictions=True,
            include_transcript_excerpts=True,
            created_at=created,
            completed_at=completed_at,
        ))

    # ── Membership for the QA user so the walkthrough screenshots work ──
    if qa_user is not None:
        for kase in seeded_cases[:3]:
            existing_mem = (await session.execute(
                select(CaseMember).where(
                    CaseMember.case_id == kase.id,
                    CaseMember.user_id == qa_user.id,
                )
            )).scalar_one_or_none()
            if existing_mem is None:
                session.add(CaseMember(
                    case_id=kase.id,
                    user_id=qa_user.id,
                    permission=CasePermission.CASE_OWNER,
                    granted_by_id=persona.id,
                ))

    print(
        "Seed complete.\n"
        f"  organisation : {org_row.name}\n"
        f"  persona      : Sarah Blackwood (admin@blackwoodlaw.com / Demo@Pass123!)\n"
        f"  qa user      : qa.tester@gmail.com / QATest2026!Secure (when present)\n"
        f"  cases        : {len(seeded_cases)}\n"
        f"  contradictions inserted on lead case : {len(CASE_BLUEPRINTS[0]['contradictions'])}\n"
        f"  total contradictions : "
        f"{sum(len(b['contradictions']) for b in CASE_BLUEPRINTS)}\n"
        f"  reports      : {len(REPORT_BLUEPRINTS)}\n"
    )


async def main() -> None:
    fresh = "--fresh" in sys.argv
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        async with session.begin():
            await seed(session, fresh=fresh)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
