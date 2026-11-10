"""Broker-approved customer update queue.

Revision ID: e50c91a72bd3
Revises: d4a916ec3082
"""

from alembic import op
import sqlalchemy as sa

revision = "e50c91a72bd3"
down_revision = "d4a916ec3082"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_contacts",
        sa.Column("customer_key", sa.String(300), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "customer_update_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_no",
            sa.Integer(),
            sa.ForeignKey("kof_loads.order_no"),
            nullable=False,
        ),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("eta", sa.String(250)),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("send_started_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
    )
    op.create_index(
        "ix_customer_update_drafts_order_no", "customer_update_drafts", ["order_no"]
    )
    op.create_index(
        "ix_customer_update_drafts_state", "customer_update_drafts", ["state"]
    )
    op.create_index(
        "uq_customer_update_pending",
        "customer_update_drafts",
        ["order_no"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
        sqlite_where=sa.text("state = 'pending'"),
    )


def downgrade():
    op.drop_table("customer_update_drafts")
    op.drop_table("customer_contacts")
