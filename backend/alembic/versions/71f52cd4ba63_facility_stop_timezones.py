"""add facility time zones to load stops

Revision ID: 71f52cd4ba63
Revises: c9e82f3a61b4
"""

from alembic import op
import sqlalchemy as sa


revision = "71f52cd4ba63"
down_revision = "c9e82f3a61b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loads", sa.Column("pickup_timezone", sa.String(64), nullable=True))
    op.add_column("loads", sa.Column("delivery_timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("loads", "delivery_timezone")
    op.drop_column("loads", "pickup_timezone")
