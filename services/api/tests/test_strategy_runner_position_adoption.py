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
from sqlalchemy import event, select
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.brokers.base import Bar, Position
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


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


class _BrokerWithExistingPosition:
    mode = "paper"

    def __init__(self, bars: list[Bar], existing: Position | None) -> None:
        self._bars = bars
        self._existing = existing

    async def get_positions(self) -> list[Position]:
        return [self._existing] if self._existing is not None else []

    def stream_bars(self, tickers: list[str], timeframe: str) -> AsyncIterator[Bar]:
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
        env=env_vars, check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


async def _seed_run(
    engine: AsyncEngine, mode: StrategyRunMode = StrategyRunMode.paper
) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(StrategyRun(
            id=run_id, strategy_key="macd_rsi_adx", ticker="SPY",
            mode=mode.value, status=StrategyRunStatus.pending.value, params={},
        ))
        await session.commit()
    return run_id


@pytest.mark.asyncio
async def test_runner_adopts_existing_long_position_on_startup(tmp_path: Path) -> None:
    db_path = tmp_path / "adopt_long.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine)

    bars = [_bar(i) for i in range(5)]
    broker = _BrokerWithExistingPosition(
        bars=bars,
        existing=Position(ticker="SPY", quantity=Decimal("10"), avg_entry_price=Decimal("99.5")),
    )

    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    assert ctx.current_position == Decimal("10")
    assert ctx.trail_state is not None
    assert ctx.trail_state.side == "long"
    assert ctx.trail_state.entry_price == Decimal("99.5")

    async with AsyncSession(engine, expire_on_commit=False) as session:
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()
    kinds = [e.event_kind for e in events]
    assert kinds[0] == "run_started"
    assert "position_adoption" in kinds
    adoption_idx = kinds.index("position_adoption")
    first_eval_idx = kinds.index("evaluate")
    assert adoption_idx < first_eval_idx


@pytest.mark.asyncio
async def test_runner_seeds_no_state_when_no_existing_position(tmp_path: Path) -> None:
    db_path = tmp_path / "adopt_flat.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine)

    bars = [_bar(i) for i in range(5)]
    broker = _BrokerWithExistingPosition(bars=bars, existing=None)

    ctx = StrategyRunnerContext(
        run_id=run_id, strategy=MacdRsiAdxStrategy(), ticker="SPY",
        mode="paper", params={}, broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    assert ctx.current_position == Decimal("0")
    assert ctx.trail_state is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_runner_adopts_existing_short_position(tmp_path: Path) -> None:
    db_path = tmp_path / "adopt_short.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine)

    bars = [_bar(i) for i in range(3)]
    broker = _BrokerWithExistingPosition(
        bars=bars,
        existing=Position(ticker="SPY", quantity=Decimal("-5"), avg_entry_price=Decimal("101.0")),
    )

    ctx = StrategyRunnerContext(
        run_id=run_id, strategy=MacdRsiAdxStrategy(), ticker="SPY",
        mode="paper", params={}, broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    assert ctx.current_position == Decimal("-5")
    assert ctx.trail_state is not None
    assert ctx.trail_state.side == "short"
    assert ctx.trail_state.entry_price == Decimal("101.0")
    await engine.dispose()
