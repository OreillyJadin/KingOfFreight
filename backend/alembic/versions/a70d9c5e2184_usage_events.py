"""Workspace usage events.

Revision ID: a70d9c5e2184
Revises: f68b429d1a03
"""

from alembic import op
import sqlalchemy as sa

revision = "a70d9c5e2184"
down_revision = "f68b429d1a03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(120), nullable=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("path", sa.String(160), nullable=True),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "device IN ('mobile', 'desktop', 'tablet')", name="ck_usage_events_device"
        ),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_table("usage_events")
