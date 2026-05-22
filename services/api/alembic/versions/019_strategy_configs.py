"""strategy_configs

Revision ID: 019
Revises: 018
Create Date: 2026-05-22 12:00:00.000000

Spec §11.1: per-(strategy_key, ticker) parameter overrides. One row per
(strategy_key, ticker) pair (uniqueness enforced). The Phase 3 sweep
inserts a best-by-net-pnl config per pair; the Phase 4 runner reads it
when starting a (strategy, ticker) runner.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019"
down_revision: str | Sequence[str] | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "strategy_key", "ticker", name="uq_strategy_configs_strategy_ticker"
        ),
    )
    op.create_index(
        "ix_strategy_configs_strategy_key", "strategy_configs", ["strategy_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_configs_strategy_key", table_name="strategy_configs")
    op.drop_table("strategy_configs")
