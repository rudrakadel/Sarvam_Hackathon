"""Row-Level Security policies for multi-tenant isolation.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-20 00:00:00.000000

For every tenant-scoped table we:

1. ENABLE ROW LEVEL SECURITY.
2. CREATE a policy that compares the row's organisation_id (directly or via a
   1-hop join to its parent) to the GUC `app.current_org_id`.

By design we do **not** `FORCE ROW LEVEL SECURITY` here, because:

- The Alembic upgrader and seed scripts connect as the table owner, and
  table owners bypass RLS unless `FORCE` is set. Forcing it during the
  migration itself would lock us out of our own upgrade.
- The test suite runs on SQLite, which has no concept of RLS.
- The app today filters by `organisation_id` in every SELECT — so app code
  works either way.

To turn RLS into a defence-in-depth enforcement (recommended for
production), run the `FORCE ROW LEVEL SECURITY` block from SECURITY.md
*after* this migration and *after* creating your production app role.

ALL operations are PostgreSQL-only. SQLite no-ops.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


# ── Table topology — how each table reaches its tenant boundary ─────────────
#
# Direct: table has its own `organisation_id` column.
# Via-case: table has `case_id`; we join cases.organisation_id.
# Via-document: table has `document_id`; we join documents.case_id and then
#     cases.organisation_id (used for document_pages).
# Via-transcript: table has `transcript_id` (used for transcript_segments).

DIRECT_ORG_TABLES = [
    "users",
    "cases",
    "audit_logs",
]

VIA_CASE_TABLES = [
    "case_members",
    "audio_files",
    "transcripts",
    "documents",
    "contradictions",
    "analysis_jobs",
    "reports",
    "nl_queries",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    # ── Helper SQL fragment ─────────────────────────────────────────────────
    # `current_setting('app.current_org_id', true)` returns NULL when the GUC
    # is not set (the `true` second arg = missing_ok). When NULL, the policy
    # comparison fails and zero rows match — exactly what we want under
    # `FORCE ROW LEVEL SECURITY` for non-tenant-aware connections.
    org_guc_sql = "current_setting('app.current_org_id', true)::uuid"

    # ── Direct tenant tables ────────────────────────────────────────────────
    for table in DIRECT_ORG_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            CREATE POLICY tenant_isolation ON {table}
                USING (organisation_id = {org_guc_sql})
                WITH CHECK (organisation_id = {org_guc_sql});
            """
        )

    # ── Via-case tables ─────────────────────────────────────────────────────
    for table in VIA_CASE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            CREATE POLICY tenant_isolation ON {table}
                USING (
                    case_id IN (
                        SELECT id FROM cases
                        WHERE organisation_id = {org_guc_sql}
                    )
                )
                WITH CHECK (
                    case_id IN (
                        SELECT id FROM cases
                        WHERE organisation_id = {org_guc_sql}
                    )
                );
            """
        )

    # ── transcript_segments — one extra hop via transcripts ─────────────────
    op.execute("ALTER TABLE transcript_segments ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        DROP POLICY IF EXISTS tenant_isolation ON transcript_segments;
        CREATE POLICY tenant_isolation ON transcript_segments
            USING (
                transcript_id IN (
                    SELECT t.id FROM transcripts t
                    JOIN cases c ON c.id = t.case_id
                    WHERE c.organisation_id = {org_guc_sql}
                )
            )
            WITH CHECK (
                transcript_id IN (
                    SELECT t.id FROM transcripts t
                    JOIN cases c ON c.id = t.case_id
                    WHERE c.organisation_id = {org_guc_sql}
                )
            );
        """
    )

    # ── document_pages — one extra hop via documents ────────────────────────
    op.execute("ALTER TABLE document_pages ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        DROP POLICY IF EXISTS tenant_isolation ON document_pages;
        CREATE POLICY tenant_isolation ON document_pages
            USING (
                document_id IN (
                    SELECT d.id FROM documents d
                    JOIN cases c ON c.id = d.case_id
                    WHERE c.organisation_id = {org_guc_sql}
                )
            )
            WITH CHECK (
                document_id IN (
                    SELECT d.id FROM documents d
                    JOIN cases c ON c.id = d.case_id
                    WHERE c.organisation_id = {org_guc_sql}
                )
            );
        """
    )

    # ── notifications — user-scoped (and users are org-scoped) ──────────────
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        DROP POLICY IF EXISTS tenant_isolation ON notifications;
        CREATE POLICY tenant_isolation ON notifications
            USING (
                user_id IN (
                    SELECT id FROM users
                    WHERE organisation_id = {org_guc_sql}
                )
            )
            WITH CHECK (
                user_id IN (
                    SELECT id FROM users
                    WHERE organisation_id = {org_guc_sql}
                )
            );
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    all_tables = (
        DIRECT_ORG_TABLES
        + VIA_CASE_TABLES
        + ["transcript_segments", "document_pages", "notifications"]
    )
    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        # Don't disable RLS — leaving it enabled with no policy is harmless
        # (every query returns zero rows under FORCE), and re-enabling is
        # cheap on the next upgrade. If you truly want to disable, run:
        #     ALTER TABLE <t> DISABLE ROW LEVEL SECURITY;
