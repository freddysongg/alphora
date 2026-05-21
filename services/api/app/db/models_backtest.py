"""SQLAlchemy models for the backtest engine outputs (spec §11.1).

The engine in `app.services.backtest_engine` is pure-function and does
not import these models; the orchestrator `run_backtest` is the only
caller that materialises engine output into these rows.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BacktestRun(Base):
    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtests_strategy_ticker", "strategy_key", "ticker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    params: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    slippage_per_share_cents: Mapped[float] = mapped_column(Float, nullable=False)
    commission_per_trade_usd: Mapped[float] = mapped_column(Float, nullable=False)
    position_size_shares: Mapped[int] = mapped_column(Integer, nullable=False)
    bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    net_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_drawdown_usd: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    backtest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("backtests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    side: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_bar_index: Mapped[int] = mapped_column(Integer, nullable=False)
    exit_bar_index: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)
    bars_held: Mapped[int] = mapped_column(Integer, nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(32), nullable=False)


class BacktestEquityPoint(Base):
    __tablename__ = "backtest_equity"
    __table_args__ = (
        UniqueConstraint("backtest_id", "day", name="uq_backtest_equity_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    backtest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("backtests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    equity_usd: Mapped[float] = mapped_column(Float, nullable=False)
    drawdown_usd: Mapped[float] = mapped_column(Float, nullable=False)
