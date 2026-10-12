"""Add notifications table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NOTIFICATION_TYPES = [
    "ANALYSIS_COMPLETE",
    "ANALYSIS_FAILED",
    "TRANSCRIPT_READY",
    "OCR_COMPLETE",
    "REPORT_READY",
    "CASE_SHARED",
    "SYSTEM",
]


def upgrade() -> None:
    notificationtype_enum = sa.Enum(
        *NOTIFICATION_TYPES,
        name="notificationtype",
    )
    notificationtype_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "type",
            sa.Enum(*NOTIFICATION_TYPES, name="notificationtype", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notificationtype").drop(op.get_bind(), checkfirst=True)
