"""strategy_runs + strategy_run_events

Revision ID: 020
Revises: 019
Create Date: 2026-05-23 12:00:00.000000

Spec §11.1 names these `runs` and `run_events`, but `run_events` already
exists in the research pipeline (see app/db/models_runs.py). Phase 4
prefixes its four new tables with `strategy_` to avoid both the SQL-level
collision and the conceptual collision between two distinct event logs.
This is the Phase 4 naming deviation.

- `strategy_runs`: one row per active (strategy_key, ticker, mode) runner.
  Status enum: pending → running → (paused | stopped | errored).
- `strategy_run_events`: append-only log of per-bar decisions, gate
  rejects, throttles, halts, fills. High-volume — indexed on (run_id, bar_ts).
  event_kind values: signal, evaluate, risk_reject, risk_throttle,
  risk_halt, judge_verdict, approval_decision, order_submit, order_fill,
  order_reject, stop_hit, eod_flatten, run_started, run_stopped, run_error.
  level values: info, warn, error.

`strategy_runs.mode` values: paper, live.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020"
down_revision: str | Sequence[str] | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_runs_strategy_ticker_mode",
        "strategy_runs",
        ["strategy_key", "ticker", "mode"],
    )
    op.create_index("ix_strategy_runs_status", "strategy_runs", ["status"])

    op.create_table(
        "strategy_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
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
        "ix_strategy_run_events_run_bar",
        "strategy_run_events",
        ["run_id", "bar_ts"],
    )
    op.create_index(
        "ix_strategy_run_events_event_kind",
        "strategy_run_events",
        ["event_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_run_events_event_kind", table_name="strategy_run_events")
    op.drop_index("ix_strategy_run_events_run_bar", table_name="strategy_run_events")
    op.drop_table("strategy_run_events")
    op.drop_index("ix_strategy_runs_status", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_strategy_ticker_mode", table_name="strategy_runs")
    op.drop_table("strategy_runs")
