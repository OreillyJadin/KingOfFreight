"""Add user accounts and KOF sync tables.

Revision ID: a9d43fcd27b1
Revises: 71f52cd4ba63
Create Date: 2026-01-13 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9d43fcd27b1"
down_revision: Union[str, None] = "71f52cd4ba63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("password_version", sa.Integer(), nullable=False),
        sa.Column("must_set_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )
    op.create_table(
        "kof_loads",
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("date_of_sale", sa.Date(), nullable=True),
        sa.Column("customer", sa.String(length=250), nullable=True),
        sa.Column("branch", sa.String(length=250), nullable=True),
        sa.Column("carrier", sa.String(length=250), nullable=True),
        sa.Column("mc", sa.String(length=40), nullable=True),
        sa.Column("origin_city", sa.String(length=150), nullable=True),
        sa.Column("origin_state", sa.String(length=40), nullable=True),
        sa.Column("origin_zip", sa.String(length=20), nullable=True),
        sa.Column("dest_city", sa.String(length=150), nullable=True),
        sa.Column("dest_state", sa.String(length=40), nullable=True),
        sa.Column("dest_zip", sa.String(length=20), nullable=True),
        sa.Column("shipper_company", sa.String(length=250), nullable=True),
        sa.Column("shipper_address", sa.Text(), nullable=True),
        sa.Column("shipper_city", sa.String(length=150), nullable=True),
        sa.Column("shipper_state", sa.String(length=40), nullable=True),
        sa.Column("shipper_zip", sa.String(length=20), nullable=True),
        sa.Column("shipper_phone", sa.String(length=80), nullable=True),
        sa.Column("shipper_email", sa.String(length=320), nullable=True),
        sa.Column("consignee_company", sa.String(length=250), nullable=True),
        sa.Column("consignee_address", sa.Text(), nullable=True),
        sa.Column("consignee_city", sa.String(length=150), nullable=True),
        sa.Column("consignee_state", sa.String(length=40), nullable=True),
        sa.Column("consignee_zip", sa.String(length=20), nullable=True),
        sa.Column("consignee_phone", sa.String(length=80), nullable=True),
        sa.Column("consignee_email", sa.String(length=320), nullable=True),
        sa.Column("pick_at", sa.DateTime(), nullable=True),
        sa.Column("pick_tz", sa.String(length=80), nullable=True),
        sa.Column("delivery_at", sa.DateTime(), nullable=True),
        sa.Column("drop_tz", sa.String(length=80), nullable=True),
        sa.Column("equipment", sa.String(length=120), nullable=True),
        sa.Column("weight", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("cost", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("profit", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("billed_status", sa.String(length=120), nullable=True),
        sa.Column("paid_status", sa.String(length=120), nullable=True),
        sa.Column("invoice_no", sa.String(length=120), nullable=True),
        sa.Column("po", sa.String(length=120), nullable=True),
        sa.Column("pu", sa.String(length=120), nullable=True),
        sa.Column("confirmation_sent", sa.Boolean(), nullable=True),
        sa.Column("confirmation_received", sa.Boolean(), nullable=True),
        sa.Column("confirmation_returned", sa.Boolean(), nullable=True),
        sa.Column("pick_status", sa.String(length=120), nullable=True),
        sa.Column("delivery_status", sa.String(length=120), nullable=True),
        sa.Column("on_time", sa.Boolean(), nullable=True),
        sa.Column("notes_text", sa.Text(), nullable=True),
        sa.Column("log_text", sa.Text(), nullable=True),
        sa.Column("booker", sa.String(length=200), nullable=True),
        sa.Column("rep", sa.String(length=200), nullable=True),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("carrier_contact_name", sa.String(length=200), nullable=True),
        sa.Column("carrier_contact_phone", sa.String(length=80), nullable=True),
        sa.Column("carrier_contact_email", sa.String(length=320), nullable=True),
        sa.Column("dispatch_contact", sa.String(length=200), nullable=True),
        sa.Column("dispatch_phone", sa.String(length=80), nullable=True),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("order_no"),
    )
    op.create_index("ix_kof_loads_stage", "kof_loads", ["stage"], unique=False)
    op.create_index(
        "ix_kof_loads_is_deleted", "kof_loads", ["is_deleted"], unique=False
    )
    op.create_index("ix_kof_loads_synced_at", "kof_loads", ["synced_at"], unique=False)
    op.create_table(
        "kof_customers",
        sa.Column("customer_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("customer_key"),
    )
    op.create_table(
        "kof_branches",
        sa.Column("branch_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("branch_key"),
    )
    op.create_table(
        "kof_list_snapshots",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "kof_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loads_upserted", sa.Integer(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kof_sync_runs_status", "kof_sync_runs", ["status"], unique=False
    )
    op.create_index(
        "uq_kof_sync_runs_single_running",
        "kof_sync_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_kof_sync_runs_single_running", table_name="kof_sync_runs")
    op.drop_index("ix_kof_sync_runs_status", table_name="kof_sync_runs")
    op.drop_table("kof_sync_runs")
    op.drop_table("kof_list_snapshots")
    op.drop_table("kof_branches")
    op.drop_table("kof_customers")
    op.drop_index("ix_kof_loads_synced_at", table_name="kof_loads")
    op.drop_index("ix_kof_loads_is_deleted", table_name="kof_loads")
    op.drop_index("ix_kof_loads_stage", table_name="kof_loads")
    op.drop_table("kof_loads")
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_table("users")
