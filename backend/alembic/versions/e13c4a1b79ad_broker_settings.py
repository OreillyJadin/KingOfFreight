"""broker settings

Revision ID: e13c4a1b79ad
Revises: bc62b29b2d0d
Create Date: 2026-10-08 21:39:00.849550
"""

from alembic import op
import sqlalchemy as sa


revision = "e13c4a1b79ad"
down_revision = "bc62b29b2d0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("broker_name", sa.String(length=100), nullable=True),
        sa.Column("broker_company", sa.String(length=100), nullable=True),
        sa.Column("broker_timezone", sa.String(length=100), nullable=True),
        sa.Column("checkin_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("no_reply_alert_minutes", sa.Integer(), nullable=True),
        sa.Column("checkin_default_channel", sa.String(length=10), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_broker_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("broker_settings")
