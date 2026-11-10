"""Encrypted assistant connection.

Revision ID: f21a80b394ce
Revises: d4e90f6a31c2
"""

import sqlalchemy as sa
from alembic import op

revision = "f21a80b394ce"
down_revision = "d4e90f6a31c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_encrypted", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_assistant_connection_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("assistant_connection")
