"""seed strategy_risk_config paper + live profile rows

Revision ID: 022
Revises: 021
Create Date: 2026-05-23 13:00:00.000000

Spec §8.1 (paper) and §8.2 (live) — both profiles MUST live as rows so
the runner can read either at startup without a race. Live values are
intentionally tight (sub-$100 starting capital + Alpaca fractional
shares).

Upgrade is idempotent: it pre-reads existing modes and skips inserts
for rows already present. This keeps sqlite round-trip tests clean and
makes re-runs safe on partially-migrated databases.

Downgrade is bounded: it only deletes the paper + live seed rows so
admin-added rows survive a downgrade/upgrade cycle.

UUID binding note: aiosqlite's sqlite3 layer cannot bind a Python
UUID object directly (it raises "type 'UUID' is not supported"), so
ids are bound as strings. psycopg3 accepts the string form equally
well, so this works across both backends.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022"
down_revision: str | Sequence[str] | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INSERT_SQL = (
    "INSERT INTO strategy_risk_config "
    "(id, mode, max_position_per_ticker_shares, "
    "max_position_per_ticker_notional_usd, max_open_positions, "
    "max_daily_loss_usd, max_consecutive_losses, "
    "daily_profit_target_usd, max_orders_per_minute_per_ticker) "
    "VALUES (:id, :mode, :shares, :notional, :open_positions, "
    ":daily_loss, :consec_losses, :profit_target, :orders_per_min)"
)


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT mode FROM strategy_risk_config")
    ).fetchall()
    existing_modes = {row[0] for row in existing}

    paper_defaults = {
        "mode": "paper",
        "max_position_per_ticker_shares": 50,
        "max_position_per_ticker_notional_usd": 5000,
        "max_open_positions": 6,
        "max_daily_loss_usd": 1000,
        "max_consecutive_losses": 5,
        "daily_profit_target_usd": 2000,
        "max_orders_per_minute_per_ticker": 3,
    }
    live_defaults = {
        "mode": "live",
        "max_position_per_ticker_shares": 0.5,
        "max_position_per_ticker_notional_usd": 25,
        "max_open_positions": 2,
        "max_daily_loss_usd": 10,
        "max_consecutive_losses": 3,
        "daily_profit_target_usd": 15,
        "max_orders_per_minute_per_ticker": 2,
    }

    for row in (paper_defaults, live_defaults):
        if row["mode"] in existing_modes:
            continue
        conn.execute(
            sa.text(_INSERT_SQL),
            {
                "id": str(uuid.uuid4()),
                "mode": row["mode"],
                "shares": row["max_position_per_ticker_shares"],
                "notional": row["max_position_per_ticker_notional_usd"],
                "open_positions": row["max_open_positions"],
                "daily_loss": row["max_daily_loss_usd"],
                "consec_losses": row["max_consecutive_losses"],
                "profit_target": row["daily_profit_target_usd"],
                "orders_per_min": row["max_orders_per_minute_per_ticker"],
            },
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM strategy_risk_config WHERE mode IN ('paper', 'live')")
    )
