"""Audit-log partitioning, pg_trgm fuzzy search, citext for emails.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-20 00:00:00.000000

Three independent improvements bundled in one revision because they're all
Postgres-extension-or-DDL work that's pointless on SQLite:

1. **pg_trgm extension + trigram GIN index on `cases.title`.** Enables
   fuzzy / typo-tolerant search (`WHERE title ILIKE '%Whitefild%'` no
   longer scans the table; the trigram index handles it).

2. **citext extension + case-insensitive uniqueness on emails.** Today
   `Sarah@firm.com` and `sarah@firm.com` are two different users — a
   security AND a UX bug. We convert `users.email` to `citext`, drop the
   old unique constraint, and add a new one on `(organisation_id, email)`
   that's case-insensitive.

3. **`audit_logs` range-partitioned by month.** The audit log has a
   7-year retention contract (NFR-15). At realistic volumes (every login,
   every case action, every contradiction review, every report download)
   that's tens of millions of rows. A non-partitioned table will hurt
   the contradiction-review write path long before year 7. Partitioning by
   month means each query against a typical "last 90 days" window scans
   3 partitions instead of the whole heap, and old partitions can be
   detached for cheap archival.

ALL operations are PostgreSQL-only. SQLite no-ops.
"""

from __future__ import annotations

from datetime import date, timedelta

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _month_range(start: date, months_forward: int) -> list[tuple[date, date]]:
    """Return [(period_start, period_start_next_month), …] for `months_forward` months."""
    ranges: list[tuple[date, date]] = []
    cur = start.replace(day=1)
    for _ in range(months_forward):
        # naive month math without dateutil — okay for [-24, +12] window
        year, month = cur.year, cur.month + 1
        if month > 12:
            year += 1
            month = 1
        nxt = date(year, month, 1)
        ranges.append((cur, nxt))
        cur = nxt
    return ranges


def upgrade() -> None:
    if not _is_postgres():
        return

    # ── 1. Extensions ───────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")

    # ── 2. Trigram index on cases.title for fuzzy search ────────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cases_title_trgm
        ON cases USING GIN (title gin_trgm_ops);
        """
    )

    # ── 3. Case-insensitive email — convert column type to citext ──────────
    #
    # Postgres can ALTER COLUMN TYPE in place when the cast is implicit.
    # citext from text is implicit. We also drop the old unique constraint
    # and recreate it because the case-sensitivity semantics change.
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN email TYPE citext USING email::citext;
        """
    )
    # The previous unique constraint name from 0001 was uq_user_org_email,
    # which targeted (organisation_id, email). Recreating it on citext keeps
    # the same composite shape but enforces case-insensitive matching.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_user_org_email;")
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT uq_user_org_email UNIQUE (organisation_id, email);
        """
    )

    # ── 4. audit_logs partitioning ─────────────────────────────────────────
    # Strategy:
    #   - rename audit_logs → audit_logs_legacy (atomic, no downtime in a
    #     transaction)
    #   - create new partitioned parent `audit_logs` with PK (id, created_at)
    #   - create monthly partitions for the past 24 months + next 12
    #   - copy legacy rows into the new partitioned table (they'll route to
    #     the right partition automatically)
    #   - drop legacy table
    #
    # Existing indexes on audit_logs (from 0001):
    #   ix_audit_org, ix_audit_case, ix_audit_created
    # We recreate them on the partitioned parent — Postgres propagates index
    # creation to all current AND future partitions when the parent declares
    # the index.

    op.execute("ALTER TABLE audit_logs RENAME TO audit_logs_legacy;")
    op.execute("ALTER INDEX ix_audit_org RENAME TO ix_audit_legacy_org;")
    op.execute("ALTER INDEX ix_audit_case RENAME TO ix_audit_legacy_case;")
    op.execute("ALTER INDEX ix_audit_created RENAME TO ix_audit_legacy_created;")

    op.execute(
        """
        CREATE TABLE audit_logs (
            id                uuid        NOT NULL DEFAULT gen_random_uuid(),
            organisation_id   uuid        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            user_id           uuid        REFERENCES users(id)        ON DELETE SET NULL,
            case_id           uuid        REFERENCES cases(id)        ON DELETE SET NULL,
            action            varchar(100) NOT NULL,
            resource_type     varchar(50),
            resource_id       varchar(255),
            detail            jsonb,
            ip_address        varchar(45),
            user_agent        varchar(500),
            created_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
        """
    )

    # Indexes on the partitioned parent — auto-applied to all partitions.
    op.execute("CREATE INDEX ix_audit_org      ON audit_logs (organisation_id);")
    op.execute("CREATE INDEX ix_audit_case     ON audit_logs (case_id);")
    op.execute("CREATE INDEX ix_audit_created  ON audit_logs (created_at);")

    # Generate 24 months back + 12 months forward of monthly partitions.
    today = date.today()
    start = date(today.year, today.month, 1) - timedelta(days=24 * 31)
    start = date(start.year, start.month, 1)
    for period_start, period_end in _month_range(start, 36):
        # Skip leftover days from the rough -24 calc
        if period_end <= today.replace(year=today.year - 3):
            continue
        part_name = f"audit_logs_y{period_start.year}m{period_start.month:02d}"
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {part_name}
            PARTITION OF audit_logs
            FOR VALUES FROM ('{period_start.isoformat()}') TO ('{period_end.isoformat()}');
            """
        )

    # Catch-all "default" partition for anything that falls outside our
    # rolling window. This protects against rogue inserts with weird
    # timestamps. Production ops should detach + archive these monthly.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs_default
        PARTITION OF audit_logs DEFAULT;
        """
    )

    # Migrate legacy rows. Insert routes them into the right monthly partition.
    op.execute(
        """
        INSERT INTO audit_logs
            (id, organisation_id, user_id, case_id, action, resource_type,
             resource_id, detail, ip_address, user_agent, created_at)
        SELECT
            id, organisation_id, user_id, case_id, action, resource_type,
            resource_id, detail, ip_address, user_agent, created_at
        FROM audit_logs_legacy;
        """
    )

    # Sanity check — the legacy and new row counts must match before we drop.
    op.execute(
        """
        DO $$
        DECLARE legacy_count bigint; new_count bigint;
        BEGIN
            SELECT count(*) INTO legacy_count FROM audit_logs_legacy;
            SELECT count(*) INTO new_count    FROM audit_logs;
            IF legacy_count <> new_count THEN
                RAISE EXCEPTION 'audit_logs partitioning row-count mismatch: legacy=%, new=%',
                    legacy_count, new_count;
            END IF;
        END $$;
        """
    )

    op.execute("DROP TABLE audit_logs_legacy;")


def downgrade() -> None:
    if not _is_postgres():
        return

    # ── Revert audit_logs to a non-partitioned table ────────────────────────
    op.execute("ALTER TABLE audit_logs RENAME TO audit_logs_partitioned;")

    op.execute(
        """
        CREATE TABLE audit_logs (
            id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id   uuid        NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            user_id           uuid        REFERENCES users(id)        ON DELETE SET NULL,
            case_id           uuid        REFERENCES cases(id)        ON DELETE SET NULL,
            action            varchar(100) NOT NULL,
            resource_type     varchar(50),
            resource_id       varchar(255),
            detail            jsonb,
            ip_address        varchar(45),
            user_agent        varchar(500),
            created_at        timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        INSERT INTO audit_logs
            (id, organisation_id, user_id, case_id, action, resource_type,
             resource_id, detail, ip_address, user_agent, created_at)
        SELECT
            id, organisation_id, user_id, case_id, action, resource_type,
            resource_id, detail, ip_address, user_agent, created_at
        FROM audit_logs_partitioned;
        """
    )
    op.execute("DROP TABLE audit_logs_partitioned;")
    op.execute("CREATE INDEX ix_audit_org      ON audit_logs (organisation_id);")
    op.execute("CREATE INDEX ix_audit_case     ON audit_logs (case_id);")
    op.execute("CREATE INDEX ix_audit_created  ON audit_logs (created_at);")

    # ── Revert citext on users.email ────────────────────────────────────────
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_user_org_email;")
    op.execute("ALTER TABLE users ALTER COLUMN email TYPE varchar(254) USING email::text;")
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT uq_user_org_email UNIQUE (organisation_id, email);
        """
    )

    # ── Drop trigram index ──────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS ix_cases_title_trgm;")

    # Keep extensions installed; dropping them affects other tools that may
    # depend on them. Safe to remove manually if desired:
    #   DROP EXTENSION pg_trgm; DROP EXTENSION citext;
