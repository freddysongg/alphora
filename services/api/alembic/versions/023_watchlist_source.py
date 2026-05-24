"""extend watchlists with source/is_active/last_built_at + watchlist_members with hypothesis_id/member_metadata

Revision ID: 023
Revises: 022
Create Date: 2026-05-23 22:00:00.000000

Adds three columns to `watchlists` (source, is_active, last_built_at) and
two columns to `watchlist_members` (hypothesis_id, member_metadata) to
support the Phase 5 universe-input layer. Existing rows backfilled via
server_default on column creation; server_default removed afterwards so
the application -- not the database -- owns the default; raw SQL inserts
that omit `source` will now fail.

Phase 5 deviation from spec §11.1: no new `daily_universe` table -- the
existing `watchlists` row IS the universe; the new `source` column
discriminates manual entries from research-driven materialization. See
.context/plans/2026-05-23-phase-5-universe.md "Critical design decision".
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "023"
down_revision: str | Sequence[str] | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("watchlists") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(16),
                nullable=False,
                server_default="manual",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "last_built_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    with op.batch_alter_table("watchlist_members") as batch_op:
        batch_op.add_column(
            sa.Column(
                "hypothesis_id",
                sa.Uuid(),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "member_metadata",
                sa.JSON(),
                nullable=True,
            ),
        )
        batch_op.create_index(
            "ix_watchlist_members_hypothesis_id",
            ["hypothesis_id"],
        )

    with op.batch_alter_table("watchlists") as batch_op:
        batch_op.alter_column("source", server_default=None)
        batch_op.alter_column("is_active", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("watchlist_members") as batch_op:
        batch_op.drop_index("ix_watchlist_members_hypothesis_id")
        batch_op.drop_column("member_metadata")
        batch_op.drop_column("hypothesis_id")

    with op.batch_alter_table("watchlists") as batch_op:
        batch_op.drop_column("last_built_at")
        batch_op.drop_column("is_active")
        batch_op.drop_column("source")
