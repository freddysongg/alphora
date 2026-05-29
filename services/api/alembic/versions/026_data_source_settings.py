"""data_source_settings

Revision ID: 026
Revises: 025
Create Date: 2026-05-27 12:00:00.000000

Per-source operator settings: enabled flag, lookback override, freeform
notes. Read by the /api/data-sources endpoints. The primary key is the
in-code registry source_key (no FK; the registry is not a table).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "026"
down_revision: str | Sequence[str] | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_source_settings",
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source_key", name="pk_data_source_settings"),
    )


def downgrade() -> None:
    op.drop_table("data_source_settings")
