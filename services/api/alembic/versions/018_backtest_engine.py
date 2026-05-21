"""backtest engine tables

Revision ID: 018
Revises: 017
Create Date: 2026-05-21 12:00:00.000000

Adds three new tables for the bar-by-bar backtest engine (spec §6.3,
§11.1): `backtests` holds one row per run with summary stats,
`backtest_trades` holds per-trade rows, `backtest_equity` holds the
daily equity-curve series.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | Sequence[str] | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("from_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("slippage_per_share_cents", sa.Float(), nullable=False),
        sa.Column("commission_per_trade_usd", sa.Float(), nullable=False),
        sa.Column("position_size_shares", sa.Integer(), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("net_pnl_usd", sa.Float(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("max_drawdown_usd", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtests_strategy_ticker", "backtests", ["strategy_key", "ticker"]
    )

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("backtest_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("entry_bar_index", sa.Integer(), nullable=False),
        sa.Column("exit_bar_index", sa.Integer(), nullable=False),
        sa.Column("entry_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("pnl_usd", sa.Float(), nullable=False),
        sa.Column("bars_held", sa.Integer(), nullable=False),
        sa.Column("exit_reason", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["backtest_id"], ["backtests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_trades_backtest_id", "backtest_trades", ["backtest_id"]
    )

    op.create_table(
        "backtest_equity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("backtest_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("equity_usd", sa.Float(), nullable=False),
        sa.Column("drawdown_usd", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["backtest_id"], ["backtests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("backtest_id", "day", name="uq_backtest_equity_day"),
    )
    op.create_index(
        "ix_backtest_equity_backtest_id", "backtest_equity", ["backtest_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_equity_backtest_id", table_name="backtest_equity")
    op.drop_table("backtest_equity")
    op.drop_index("ix_backtest_trades_backtest_id", table_name="backtest_trades")
    op.drop_table("backtest_trades")
    op.drop_index("ix_backtests_strategy_ticker", table_name="backtests")
    op.drop_table("backtests")
