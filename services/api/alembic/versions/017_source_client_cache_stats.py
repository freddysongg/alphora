"""research_runs.source_client_cache_stats

Revision ID: 017
Revises: 016
Create Date: 2026-05-20 22:00:00.000000

Persist per-run RequestCache hits/misses/evictions/hit_rate snapshot so the
cost ledger UI can surface source-client cache effectiveness next to the
OpenAI prompt-cache numbers.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017"
down_revision: str | Sequence[str] | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.add_column(
            sa.Column("source_client_cache_stats", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.drop_column("source_client_cache_stats")
