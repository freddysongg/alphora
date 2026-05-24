"""Regression coverage for Phase 4 follow-up fixes:

- The runner must pass resampled secondary-timeframe bars to strategies
  that declare any in `secondary_timeframes` (gap in the original Task 14
  wiring where `secondary_bars={}` was hardcoded).
- The runner must pass a bias-only view of `current_position` to
  `evaluate()` so fractional shares (live-profile sizing) don't collapse
  to `0` via `int(Decimal("0.5"))`.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.brokers.base import Bar, Position
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


def _bar(i: int) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal(str(100.0 + i * 0.1)),
        high=Decimal(str(100.2 + i * 0.1)),
        low=Decimal(str(99.8 + i * 0.1)),
        close=Decimal(str(100.0 + i * 0.1)),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=i),
    )


class _RecordingBroker:
    mode: str = "paper"

    def __init__(self, bars: list[Bar], positions: list[Position] | None = None) -> None:
        self._bars = bars
        self._positions = positions or []

    async def get_positions(self) -> list[Position]:
        return list(self._positions)

    def stream_bars(self, tickers: list[str], timeframe: Timeframe) -> AsyncIterator[Bar]:
        async def _gen() -> AsyncIterator[Bar]:
            for b in self._bars:
                yield b

        return _gen()


def _build_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn: DBAPIConnection, _: ConnectionPoolEntry) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _migrate(db_path: Path) -> None:
    env_vars = os.environ.copy()
    env_vars["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    subprocess.run(
        [".venv/bin/python", "-m", "alembic", "upgrade", "head"],
        env=env_vars,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


async def _seed_run(engine: AsyncEngine, strategy_key: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key=strategy_key,
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()
    return run_id


class _SecondaryRecordingStrategy:
    """Records every `secondary_bars` payload + `current_position` value the
    runner passes. Always emits target=0 so no orders fire."""

    key: str = "secondary_recorder"
    name: str = "Secondary Recorder"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = ["5min"]  # noqa: RUF012
    requires_rth: bool = False

    def __init__(self) -> None:
        self.received_secondary: list[dict[Timeframe, Bars]] = []
        self.received_positions: list[int] = []

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        del primary_bars, params
        self.received_secondary.append(dict(secondary_bars))
        self.received_positions.append(current_position)
        return StrategyResult(target=0, meta={})


@pytest.mark.asyncio
async def test_runner_resamples_secondary_timeframes_when_strategy_declares_them(
    tmp_path: Path,
) -> None:
    """A strategy with `secondary_timeframes=['5min']` must receive a
    populated 5min DataFrame each bar (not the empty dict the original
    Task 14 wiring passed)."""
    db_path = tmp_path / "secondary.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    strategy = _SecondaryRecordingStrategy()
    run_id = await _seed_run(engine, strategy.key)

    bars = [_bar(i) for i in range(7)]
    broker = _RecordingBroker(bars)
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=strategy,
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)
    await engine.dispose()

    assert len(strategy.received_secondary) == len(bars)
    for payload in strategy.received_secondary:
        assert "5min" in payload, (
            "runner must populate secondary_bars for declared timeframes"
        )
    final_5m = strategy.received_secondary[-1]["5min"]
    assert list(final_5m.columns) == ["open", "high", "low", "close", "volume"]
    assert len(final_5m) >= 1


class _PositionBiasRecorder:
    """Records the `current_position` value passed by the runner. Emits
    target=0 so no orders fire."""

    key: str = "bias_recorder"
    name: str = "Bias Recorder"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = False

    def __init__(self) -> None:
        self.received_positions: list[int] = []

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        del primary_bars, secondary_bars, params
        self.received_positions.append(current_position)
        return StrategyResult(target=0, meta={})


@pytest.mark.asyncio
async def test_runner_passes_bias_sign_not_truncated_int_for_fractional_position(
    tmp_path: Path,
) -> None:
    """A 0.5-share long position must surface as `current_position=1` (the
    sign), not `int(Decimal("0.5"))=0`. Otherwise a strategy in
    sub-1-share live mode treats a real holding as flat."""
    db_path = tmp_path / "fractional.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    strategy = _PositionBiasRecorder()
    run_id = await _seed_run(engine, strategy.key)

    bars = [_bar(i) for i in range(3)]
    broker = _RecordingBroker(
        bars,
        positions=[
            Position(
                ticker="SPY",
                quantity=Decimal("0.5"),
                avg_entry_price=Decimal("500"),
            )
        ],
    )
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=strategy,
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)
    await engine.dispose()

    assert ctx.current_position == Decimal("0.5"), (
        "runner must preserve fractional position internally"
    )
    assert all(p == 1 for p in strategy.received_positions), (
        "strategy must see bias=+1 for a 0.5-share long, not 0 (truncated int)"
    )


@pytest.mark.asyncio
async def test_runner_passes_bias_sign_for_fractional_short(tmp_path: Path) -> None:
    db_path = tmp_path / "fractional_short.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    strategy = _PositionBiasRecorder()
    run_id = await _seed_run(engine, strategy.key)

    broker = _RecordingBroker(
        [_bar(i) for i in range(2)],
        positions=[
            Position(
                ticker="SPY",
                quantity=Decimal("-0.3"),
                avg_entry_price=Decimal("510"),
            )
        ],
    )
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=strategy,
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)
    await engine.dispose()

    assert all(p == -1 for p in strategy.received_positions)
