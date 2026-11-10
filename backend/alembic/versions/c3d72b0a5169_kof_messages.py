"""KOF driver text threads.

Revision ID: c3d72b0a5169
Revises: b8a270d43e19
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d72b0a5169"
down_revision = "b8a270d43e19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kof_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_no", sa.Integer(), sa.ForeignKey("kof_loads.order_no"), nullable=True
        ),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("to_phone", sa.String(16), nullable=True),
        sa.Column("from_phone", sa.String(16), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(100), unique=True, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_method", sa.String(40), nullable=True),
        sa.Column("candidate_order_nos", sa.JSON(), nullable=False),
        sa.Column("parsed_status", sa.String(30), nullable=True),
        sa.Column("parsed_eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_summary", sa.Text(), nullable=True),
    )
    for column in ("order_no", "to_phone", "created_at"):
        op.create_index(f"ix_kof_messages_{column}", "kof_messages", [column])


def downgrade() -> None:
    op.drop_table("kof_messages")
