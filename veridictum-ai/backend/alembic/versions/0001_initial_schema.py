"""Initial schema — all VeriDictum AI tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Pre-create all ENUM types so sa.Enum(create_type=False) in create_table works
ENUM_DEFINITIONS = [
    ("userrole",            ["ADMIN", "ATTORNEY", "PARALEGAL", "VIEWER"]),
    ("accountstatus",       ["PENDING_VERIFICATION", "ACTIVE", "SUSPENDED", "LOCKED", "DELETED"]),
    ("subscriptiontier",    ["FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"]),
    ("casestatus",          ["ACTIVE", "ARCHIVED", "CLOSED"]),
    ("casetype",            ["CRIMINAL", "CIVIL", "DEPOSITION", "ARBITRATION", "HEARING", "OTHER"]),
    ("casepermission",      ["VIEWER", "EDITOR", "CASE_OWNER"]),
    ("processingstatus",    ["PENDING", "QUEUED", "PROCESSING", "COMPLETED", "FAILED", "RETRYING"]),
    ("contradictionseverity", ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]),
    ("contradictionstatus", ["AI_SUGGESTED", "CONFIRMED", "REJECTED", "NEEDS_REVIEW"]),
    ("reportstatus",        ["PENDING", "GENERATING", "READY", "FAILED"]),
]


def _enum(name: str) -> postgresql.ENUM:
    """Return a PostgreSQL ENUM reference without creating the type (already created by op.execute)."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    # ── Create all ENUM types (idempotent) ───────────────────────────────────
    for type_name, values in ENUM_DEFINITIONS:
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({vals})")

    # ── organisations ────────────────────────────────────────────────────────
    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("subscription_tier", _enum("subscriptiontier"),
                  nullable=False, server_default="FREE"),
        sa.Column("max_users", sa.Integer, nullable=False, server_default="5"),
        sa.Column("max_cases", sa.Integer, nullable=False, server_default="10"),
        sa.Column("max_storage_gb", sa.Integer, nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("role", _enum("userrole"), nullable=False, server_default="VIEWER"),
        sa.Column("account_status", _enum("accountstatus"),
                  nullable=False, server_default="PENDING_VERIFICATION"),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("email_verify_token_hash", sa.String(255)),
        sa.Column("email_verify_expires_at", sa.DateTime(timezone=True)),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mfa_secret", sa.String(255)),
        sa.Column("backup_codes_hash", postgresql.ARRAY(sa.String),
                  nullable=False, server_default="{}"),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_ip", sa.String(45)),
        sa.Column("password_reset_token_hash", sa.String(255)),
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("organisation_id", "email", name="uq_user_org_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── user_sso_links ───────────────────────────────────────────────────────
    op.create_table(
        "user_sso_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text),
        sa.Column("refresh_token_encrypted", sa.Text),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_sso_provider_uid"),
    )

    # ── refresh_tokens ───────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_hash", "refresh_tokens", ["token_hash"])

    # ── invitations ──────────────────────────────────────────────────────────
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", _enum("userrole"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── cases ────────────────────────────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("case_number", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("court", sa.String(255)),
        sa.Column("jurisdiction", sa.String(255)),
        sa.Column("case_type", _enum("casetype"), nullable=False, server_default="OTHER"),
        sa.Column("status", _enum("casestatus"), nullable=False, server_default="ACTIVE"),
        sa.Column("description", sa.Text),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "case_number", name="uq_case_org_number"),
    )
    op.create_index("ix_cases_org", "cases", ["organisation_id"])

    # ── case_members ─────────────────────────────────────────────────────────
    op.create_table(
        "case_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission", _enum("casepermission"), nullable=False, server_default="VIEWER"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("added_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("case_id", "user_id", name="uq_case_member"),
    )

    # ── audio_files ──────────────────────────────────────────────────────────
    op.create_table(
        "audio_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("blob_name", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("language_hint", sa.String(10)),
        sa.Column("speaker_count_hint", sa.Integer),
        sa.Column("processing_status", _enum("processingstatus"),
                  nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── transcripts ──────────────────────────────────────────────────────────
    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("audio_file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language_detected", sa.String(10)),
        sa.Column("model_used", sa.String(100), server_default="whisper-large-v3"),
        sa.Column("word_count", sa.Integer, server_default="0"),
        sa.Column("speaker_count", sa.Integer, server_default="0"),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("full_text", sa.Text),
        sa.Column("full_text_tsv", postgresql.TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_transcripts_tsv", "transcripts", ["full_text_tsv"],
                    postgresql_using="gin")

    # ── transcript_segments ──────────────────────────────────────────────────
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker_label", sa.String(50), nullable=False),
        sa.Column("speaker_name", sa.String(255)),
        sa.Column("start_time", sa.Float, nullable=False),
        sa.Column("end_time", sa.Float, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("is_edited", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("original_text", sa.Text),
        sa.Column("edited_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_segments_transcript", "transcript_segments", ["transcript_id"])

    # ── documents ────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("blob_name", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer),
        sa.Column("processing_status", _enum("processingstatus"),
                  nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── document_pages ───────────────────────────────────────────────────────
    op.create_table(
        "document_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text),
        sa.Column("text_tsv", postgresql.TSVECTOR),
        sa.Column("confidence", sa.Float),
        sa.Column("bounding_boxes", postgresql.JSONB),
        sa.Column("is_corrected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("corrected_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("corrected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "page_number", name="uq_doc_page"),
    )
    op.create_index("ix_doc_pages_tsv", "document_pages", ["text_tsv"],
                    postgresql_using="gin")

    # ── contradictions ───────────────────────────────────────────────────────
    op.create_table(
        "contradictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", _enum("contradictionseverity"), nullable=False),
        sa.Column("status", _enum("contradictionstatus"),
                  nullable=False, server_default="AI_SUGGESTED"),
        sa.Column("source_a_type", sa.String(20), nullable=False),
        sa.Column("source_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_a_excerpt", sa.Text, nullable=False),
        sa.Column("source_a_timestamp", sa.Float),
        sa.Column("source_a_page", sa.Integer),
        sa.Column("source_a_speaker", sa.String(255)),
        sa.Column("source_b_type", sa.String(20), nullable=False),
        sa.Column("source_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_b_excerpt", sa.Text, nullable=False),
        sa.Column("source_b_timestamp", sa.Float),
        sa.Column("source_b_page", sa.Integer),
        sa.Column("source_b_speaker", sa.String(255)),
        sa.Column("ai_explanation", sa.Text, nullable=False),
        sa.Column("ai_confidence", sa.Float, nullable=False),
        sa.Column("attorney_note", sa.Text),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_contradictions_case", "contradictions", ["case_id"])

    # ── analysis_jobs ────────────────────────────────────────────────────────
    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("status", _enum("processingstatus"),
                  nullable=False, server_default="PENDING"),
        sa.Column("contradictions_found", sa.Integer, server_default="0"),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("model_used", sa.String(100)),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── reports ──────────────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", _enum("reportstatus"), nullable=False, server_default="PENDING"),
        sa.Column("blob_name", sa.String(1000)),
        sa.Column("sas_url", sa.Text),
        sa.Column("sas_expires_at", sa.DateTime(timezone=True)),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("page_count", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # ── nl_queries ───────────────────────────────────────────────────────────
    op.create_table(
        "nl_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asked_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("answer_text", sa.Text),
        sa.Column("citations", postgresql.JSONB, server_default="[]"),
        sa.Column("model_used", sa.String(100)),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("response_time_ms", sa.Integer),
        sa.Column("retrieval_method", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # ── audit_logs ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cases.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("detail", postgresql.JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_audit_org",     "audit_logs", ["organisation_id"])
    op.create_index("ix_audit_case",    "audit_logs", ["case_id"])
    op.create_index("ix_audit_created", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("nl_queries")
    op.drop_table("reports")
    op.drop_table("analysis_jobs")
    op.drop_table("contradictions")
    op.drop_table("document_pages")
    op.drop_table("documents")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.drop_table("audio_files")
    op.drop_table("case_members")
    op.drop_table("cases")
    op.drop_table("invitations")
    op.drop_table("refresh_tokens")
    op.drop_table("user_sso_links")
    op.drop_table("users")
    op.drop_table("organisations")

    for type_name, _ in reversed(ENUM_DEFINITIONS):
        op.execute(f"DROP TYPE IF EXISTS {type_name}")
