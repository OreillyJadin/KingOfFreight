"""User roles, account activity and last login.

Revision ID: f68b429d1a03
Revises: e50c91a72bd3
"""

from alembic import op
import sqlalchemy as sa

revision = "f68b429d1a03"
down_revision = "e50c91a72bd3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("role", sa.String(20), nullable=False, server_default="member")
        )
        batch.add_column(
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
        batch.add_column(
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint("ck_users_role", "role IN ('admin', 'member')")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_role", type_="check")
        batch.drop_column("last_login_at")
        batch.drop_column("is_active")
        batch.drop_column("role")
