"""Store BOL PDFs in Postgres.

Downgrading restores the old path columns but does not restore PDF files.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "c9e82f3a61b4"
down_revision = "e13c4a1b79ad"
branch_labels = None
depends_on = None

_ATTACHMENT_FK = "fk_communications_attachment_file_id_bol_files"


def _display_filename(stored_path: str) -> str:
    original = Path(stored_path).name
    stripped = re.sub(r"^\d{20}-", "", original)
    return (stripped or original)[:255]


def upgrade() -> None:
    op.create_table(
        "bol_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("communications") as batch:
        batch.add_column(sa.Column("attachment_file_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("attachment_filename", sa.String(length=255), nullable=True)
        )
        batch.create_foreign_key(
            _ATTACHMENT_FK,
            "bol_files",
            ["attachment_file_id"],
            ["id"],
            ondelete="SET NULL",
        )

    bind = op.get_bind()
    communications = sa.table(
        "communications",
        sa.column("id", sa.Integer),
        sa.column("attachment_path", sa.String),
        sa.column("attachment_file_id", sa.Integer),
        sa.column("attachment_filename", sa.String),
    )
    bol_files = sa.table(
        "bol_files",
        sa.column("id", sa.Integer),
        sa.column("filename", sa.String),
        sa.column("content", sa.LargeBinary),
        sa.column("size_bytes", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    fallback_dir = Path(os.environ.get("UPLOAD_DIR", "./data/uploads"))
    rows = bind.execute(
        sa.select(communications.c.id, communications.c.attachment_path).where(
            communications.c.attachment_path.is_not(None)
        )
    )
    for communication_id, stored_path in rows:
        source = Path(stored_path)
        if not source.is_file():
            source = fallback_dir / Path(stored_path).name
        if not source.is_file():
            print(
                f"WARNING: BOL file for communication {communication_id} was not found at "
                f"{stored_path!r} or {source}; leaving it unattached."
            )
            continue

        content = source.read_bytes()
        result = bind.execute(
            bol_files.insert()
            .values(
                filename=_display_filename(stored_path),
                content=content,
                size_bytes=len(content),
                created_at=datetime.now(timezone.utc),
            )
            .returning(bol_files.c.id)
        )
        file_id = result.scalar_one()
        bind.execute(
            communications.update()
            .where(communications.c.id == communication_id)
            .values(
                attachment_file_id=file_id,
                attachment_filename=_display_filename(stored_path),
            )
        )

    with op.batch_alter_table("communications") as batch:
        batch.drop_column("attachment_path")

    with op.batch_alter_table("loads") as batch:
        batch.drop_column("bol_file_path")


def downgrade() -> None:
    with op.batch_alter_table("communications") as batch:
        batch.add_column(
            sa.Column("attachment_path", sa.String(length=500), nullable=True)
        )
        batch.drop_constraint(_ATTACHMENT_FK, type_="foreignkey")
        batch.drop_column("attachment_filename")
        batch.drop_column("attachment_file_id")

    with op.batch_alter_table("loads") as batch:
        batch.add_column(
            sa.Column("bol_file_path", sa.String(length=500), nullable=True)
        )

    op.drop_table("bol_files")
