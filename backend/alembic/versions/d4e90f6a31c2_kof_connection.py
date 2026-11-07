"""Store KOF connection credentials for the broker.

Revision ID: d4e90f6a31c2
Revises: a9d43fcd27b1
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e90f6a31c2"
down_revision = "a9d43fcd27b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kof_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_kof_connection_singleton"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("kof_connection")
