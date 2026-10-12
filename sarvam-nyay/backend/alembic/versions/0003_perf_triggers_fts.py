"""Performance: updated_at trigger, GIN FTS, composite indexes, CHECK constraints.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20 00:00:00.000000

This migration is the "production-ready" pass on the schema:

1. Adds a Postgres trigger (`set_updated_at`) that auto-updates every
   `updated_at` column on row UPDATE — no application-side coordination needed.
2. Creates GIN tsvector indexes on transcripts and documents for true
   PostgreSQL full-text search (the 3-pass RAG engine claims this in its
   docstring; this migration is what makes that claim real).
3. Adds composite indexes on the hot query paths surfaced by the dashboard,
   case detail, and contradictions list endpoints.
4. Adds CHECK constraints on numeric ranges that have no business being out
   of bounds (confidence scores in [0,1], severity counts >= 0).

ALL operations are PostgreSQL-only. SQLite (used for unit tests and local dev)
silently no-ops because triggers/GIN/tsvector are PG-specific features. The
guard at the top of each function reads the live dialect from alembic's bind.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite path: no triggers, no GIN, no tsvector. Tests run on SQLite and
        # exercise the application layer; the production guarantees come from
        # this migration only when running on PostgreSQL.
        return

    # ── 1. Generic updated_at trigger ────────────────────────────────────────
    # One function, attached as a row-level BEFORE UPDATE trigger to every
    # table that owns an `updated_at` column. Replaces the implicit
    # `onupdate=func.now()` in SQLAlchemy with a DB-level guarantee, which
    # protects against direct SQL updates that bypass the ORM.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    tables_with_updated_at = [
        "organisations",
        "users",
        "cases",
        "audio_files",
        "transcripts",
        "documents",
        "contradictions",
    ]
    for table in tables_with_updated_at:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION set_updated_at();
            """
        )

    # ── 2. Full-text search via tsvector + GIN ───────────────────────────────
    # Add a generated tsvector column to transcripts and documents, then a GIN
    # index over it. This is what the README/query_service has been promising;
    # without it the "Pass 2" FTS in the 3-pass RAG engine falls through to
    # sequential scan + plainto_tsquery, which is correct but slow at scale.
    op.execute(
        """
        ALTER TABLE transcripts
        ADD COLUMN IF NOT EXISTS full_text_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(full_text, ''))) STORED;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_transcripts_full_text_gin
        ON transcripts USING GIN (full_text_tsv);
        """
    )

    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS extracted_text_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(extracted_text, ''))) STORED;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_extracted_text_gin
        ON documents USING GIN (extracted_text_tsv);
        """
    )

    # ── 3. Composite indexes on hot query paths ──────────────────────────────
    # contradictions list filtered by case + severity (Contradictions tab) and
    # case + status (Contradictions tab pending-review filter).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contradictions_case_severity
        ON contradictions (case_id, severity);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contradictions_case_status
        ON contradictions (case_id, status);
        """
    )
    # case list scoped by org + status (Cases page filter)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cases_org_status
        ON cases (organisation_id, status);
        """
    )
    # audio + document processing dashboard (queue counts)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audio_files_case_status
        ON audio_files (case_id, status);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_case_status
        ON documents (case_id, status);
        """
    )
    # reports list scoped by case + status (Reports tab on case detail)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_reports_case_status
        ON reports (case_id, status);
        """
    )
    # notifications inbox — unread per user, ordered by recency
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notifications_user_unread_created
        ON notifications (user_id, is_read, created_at DESC);
        """
    )

    # ── 4. CHECK constraints — domain integrity at the DB layer ──────────────
    # Confidence is a probability and must live in [0, 1].
    op.execute(
        """
        ALTER TABLE contradictions
        ADD CONSTRAINT ck_contradictions_confidence_range
        CHECK (confidence_score >= 0 AND confidence_score <= 1);
        """
    )
    # OCR average confidence — same range.
    op.execute(
        """
        ALTER TABLE documents
        ADD CONSTRAINT ck_documents_avg_confidence_range
        CHECK (avg_confidence IS NULL OR (avg_confidence >= 0 AND avg_confidence <= 1));
        """
    )
    # Page number must be positive when present.
    op.execute(
        """
        ALTER TABLE contradictions
        ADD CONSTRAINT ck_contradictions_document_page_positive
        CHECK (document_page IS NULL OR document_page > 0);
        """
    )
    # File sizes must be non-negative.
    op.execute(
        """
        ALTER TABLE audio_files
        ADD CONSTRAINT ck_audio_files_size_nonneg
        CHECK (file_size_bytes >= 0);
        """
    )
    op.execute(
        """
        ALTER TABLE documents
        ADD CONSTRAINT ck_documents_size_nonneg
        CHECK (file_size_bytes >= 0);
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    # Drop CHECK constraints
    op.execute("ALTER TABLE contradictions DROP CONSTRAINT IF EXISTS ck_contradictions_confidence_range;")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_avg_confidence_range;")
    op.execute("ALTER TABLE contradictions DROP CONSTRAINT IF EXISTS ck_contradictions_document_page_positive;")
    op.execute("ALTER TABLE audio_files DROP CONSTRAINT IF EXISTS ck_audio_files_size_nonneg;")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_size_nonneg;")

    # Drop composite indexes
    op.execute("DROP INDEX IF EXISTS ix_contradictions_case_severity;")
    op.execute("DROP INDEX IF EXISTS ix_contradictions_case_status;")
    op.execute("DROP INDEX IF EXISTS ix_cases_org_status;")
    op.execute("DROP INDEX IF EXISTS ix_audio_files_case_status;")
    op.execute("DROP INDEX IF EXISTS ix_documents_case_status;")
    op.execute("DROP INDEX IF EXISTS ix_reports_case_status;")
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_unread_created;")

    # Drop GIN indexes + generated tsvector columns
    op.execute("DROP INDEX IF EXISTS ix_documents_extracted_text_gin;")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS extracted_text_tsv;")
    op.execute("DROP INDEX IF EXISTS ix_transcripts_full_text_gin;")
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS full_text_tsv;")

    # Drop triggers + function
    tables_with_updated_at = [
        "organisations",
        "users",
        "cases",
        "audio_files",
        "transcripts",
        "documents",
        "contradictions",
    ]
    for table in tables_with_updated_at:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
