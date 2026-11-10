"""Shared-login operator identities.

Revision ID: b81e0d6f3295
Revises: a70d9c5e2184
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "b81e0d6f3295"
down_revision = "a70d9c5e2184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_team_members_name_ci", "team_members", [sa.text("lower(name)")], unique=True
    )
    op.bulk_insert(
        table,
        [
            {"name": name, "is_active": True, "created_at": datetime.now(timezone.utc)}
            for name in ("Scotti", "Tony", "Kolby")
        ],
    )
    with op.batch_alter_table("usage_events") as batch:
        batch.add_column(sa.Column("team_member_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("operator_name", sa.String(120), nullable=True))
        batch.create_foreign_key(
            "fk_usage_events_team_member",
            "team_members",
            ["team_member_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_events") as batch:
        batch.drop_constraint("fk_usage_events_team_member", type_="foreignkey")
        batch.drop_column("operator_name")
        batch.drop_column("team_member_id")
    op.drop_index("ix_team_members_name_ci", table_name="team_members")
    op.drop_table("team_members")
