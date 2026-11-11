"""Request health metrics and compact daily usage history."""

from alembic import op
import sqlalchemy as sa

revision = "d03af21982bc"
down_revision = "c92f1e7043a6"
branch_labels = None
depends_on = None


def actor_columns():
    return [
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("username", sa.String(120)),
        sa.Column(
            "team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="SET NULL"),
        ),
        sa.Column("operator_name", sa.String(120)),
    ]


def upgrade():
    op.add_column(
        "usage_minutes", sa.Column("last_seen_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "request_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        *actor_columns(),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("message", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_metrics_created_at", "request_metrics", ["created_at"])
    op.create_table(
        "usage_daily",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        *actor_columns(),
        sa.Column("active_minutes", sa.Integer(), nullable=False),
        sa.Column("actions", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_usage_daily_day", "usage_daily", ["day"])


def downgrade():
    op.drop_column("usage_minutes", "last_seen_at")
    op.drop_table("usage_daily")
    op.drop_table("request_metrics")
