"""Delegated Outlook connection and email order linkage.

Revision ID: d4a916ec3082
Revises: c3d72b0a5169
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a916ec3082"
down_revision = "c3d72b0a5169"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outlook_app",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_outlook_app_singleton"),
    )
    op.create_table(
        "outlook_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("needs_reconnect", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_outlook_connection_singleton"),
    )
    op.create_table(
        "email_poll_state",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("last_poll", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("communications") as batch:
        batch.add_column(sa.Column("kof_order_no", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_communications_kof_order", "kof_loads", ["kof_order_no"], ["order_no"]
        )
        batch.create_index("ix_communications_kof_order_no", ["kof_order_no"])


def downgrade():
    with op.batch_alter_table("communications") as batch:
        batch.drop_index("ix_communications_kof_order_no")
        batch.drop_constraint("fk_communications_kof_order", type_="foreignkey")
        batch.drop_column("kof_order_no")
    op.drop_table("email_poll_state")
    op.drop_table("outlook_connection")
    op.drop_table("outlook_app")
