"""Encrypted Twilio connection.

Revision ID: b8a270d43e19
Revises: f21a80b394ce
"""

import sqlalchemy as sa
from alembic import op

revision = "b8a270d43e19"
down_revision = "f21a80b394ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twilio_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_sid", sa.String(34), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("from_number", sa.String(16), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_twilio_connection_singleton"),
    )


def downgrade() -> None:
    op.drop_table("twilio_connection")
