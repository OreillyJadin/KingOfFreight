"""Active usage minutes.

Revision ID: c92f1e7043a6
Revises: b81e0d6f3295
"""

from alembic import op
import sqlalchemy as sa

revision = "c92f1e7043a6"
down_revision = "b81e0d6f3295"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_minutes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity", sa.String(120), nullable=False),
        sa.Column("minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", sa.String(160), nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("username", sa.String(120)),
        sa.Column(
            "team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="SET NULL"),
        ),
        sa.Column("operator_name", sa.String(120)),
        sa.Column("device", sa.String(10), nullable=False),
        sa.UniqueConstraint(
            "identity", "minute", name="uq_usage_minutes_identity_minute"
        ),
        sa.CheckConstraint(
            "device IN ('mobile', 'desktop', 'tablet')", name="ck_usage_minutes_device"
        ),
    )
    op.create_index("ix_usage_minutes_minute", "usage_minutes", ["minute"])


def downgrade() -> None:
    op.drop_index("ix_usage_minutes_minute", table_name="usage_minutes")
    op.drop_table("usage_minutes")
