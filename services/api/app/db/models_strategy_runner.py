"""SQLAlchemy models for Phase 4 strategy-runner tables (spec §11.1).

Four tables, all `strategy_`-prefixed to avoid collision with the
existing research-pipeline tables (`research_runs`, `run_events`):

- `strategy_runs` — one row per active (strategy_key, ticker, mode) run.
- `strategy_run_events` — append-only per-bar decision/gate log.
- `strategy_risk_config` — singleton-ish: one row per mode (paper, live).
- `strategy_live_orders` — broker order mirror + reconciliation state.

This file holds all four models because they're tightly coupled by FK
(`strategy_run_events.run_id → strategy_runs.id`,
`strategy_live_orders.run_id → strategy_runs.id`). Keeping them together
matches the file-per-feature pattern used elsewhere in `app/db/`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    stopped = "stopped"
    errored = "errored"


class StrategyRunMode(StrEnum):
    paper = "paper"
    live = "live"


class StrategyRunEventLevel(StrEnum):
    info = "info"
    warn = "warn"
    error = "error"


class StrategyLiveOrderStatus(StrEnum):
    pending = "pending"
    submitted = "submitted"
    partially_filled = "partially_filled"
    filled = "filled"
    canceled = "canceled"
    rejected = "rejected"


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    params: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_strategy_runs_strategy_ticker_mode",
            "strategy_key",
            "ticker",
            "mode",
        ),
        Index("ix_strategy_runs_status", "status"),
    )


class StrategyRunEvent(Base):
    __tablename__ = "strategy_run_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False
    )
    bar_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_strategy_run_events_run_bar", "run_id", "bar_ts"),
        Index("ix_strategy_run_events_event_kind", "event_kind"),
    )


class StrategyRiskConfig(Base):
    """Per-mode risk caps. One row per mode name ('paper', 'live')."""
    __tablename__ = "strategy_risk_config"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    mode: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    max_position_per_ticker_shares: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    max_position_per_ticker_notional_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    max_open_positions: Mapped[int] = mapped_column(nullable=False)
    max_daily_loss_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    max_consecutive_losses: Mapped[int] = mapped_column(nullable=False)
    daily_profit_target_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    max_orders_per_minute_per_ticker: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class StrategyLiveOrder(Base):
    """Broker order mirror. mode column distinguishes paper from live."""
    __tablename__ = "strategy_live_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    avg_fill_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_strategy_live_orders_run", "run_id"),
        Index("ix_strategy_live_orders_broker_order", "broker_order_id"),
    )


__all__ = [
    "StrategyLiveOrder",
    "StrategyLiveOrderStatus",
    "StrategyRiskConfig",
    "StrategyRun",
    "StrategyRunEvent",
    "StrategyRunEventLevel",
    "StrategyRunMode",
    "StrategyRunStatus",
]
