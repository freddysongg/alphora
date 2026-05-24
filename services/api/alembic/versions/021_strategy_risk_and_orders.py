"""strategy_risk_config + strategy_live_orders

Revision ID: 021
Revises: 020
Create Date: 2026-05-23 12:30:00.000000

- `strategy_risk_config`: per-mode singleton row. Unique on `mode`.
  Mirrors spec §8.1 (paper) + §8.2 (live).
- `strategy_live_orders`: broker order mirror + reconciliation state.
  FK on `run_id` cascades on delete (runs own their orders).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "021"
down_revision: str | Sequence[str] | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_risk_config",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column(
            "max_position_per_ticker_shares", sa.Numeric(18, 6), nullable=False
        ),
        sa.Column(
            "max_position_per_ticker_notional_usd", sa.Numeric(18, 2), nullable=False
        ),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("max_daily_loss_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_consecutive_losses", sa.Integer(), nullable=False),
        sa.Column("daily_profit_target_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_orders_per_minute_per_ticker", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mode", name="uq_strategy_risk_config_mode"),
    )

    op.create_table(
        "strategy_live_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("client_order_id", sa.String(64), nullable=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Numeric(18, 6), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_qty", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["strategy_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_live_orders_run", "strategy_live_orders", ["run_id"]
    )
    op.create_index(
        "ix_strategy_live_orders_broker_order",
        "strategy_live_orders",
        ["broker_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_live_orders_broker_order", table_name="strategy_live_orders")
    op.drop_index("ix_strategy_live_orders_run", table_name="strategy_live_orders")
    op.drop_table("strategy_live_orders")
    op.drop_table("strategy_risk_config")
