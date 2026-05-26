from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.brokers.base import Bar, Position, TradabilityCheck
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


class _StubBroker:
    """Yields a fixed sequence of bars, then completes."""
    mode: str = "paper"

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def get_positions(self) -> list[Position]:
        return []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        return TradabilityCheck(
            ticker=ticker,
            is_tradable=True,
            is_shortable=True,
            is_halted=False,
            fractionable=True,
        )

    def stream_bars(self, tickers: list[str], timeframe: str) -> AsyncIterator[Bar]:
        async def _gen() -> AsyncIterator[Bar]:
            for b in self._bars:
                yield b
        return _gen()


def _build_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn: Any, _: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


async def _migrate_then_seed_run(db_path: Path) -> uuid.UUID:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    subprocess.run(
        [".venv/bin/python", "-m", "alembic", "upgrade", "head"],
        env=env, check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(StrategyRun(
            id=run_id,
            strategy_key="macd_rsi_adx",
            ticker="SPY",
            mode=StrategyRunMode.paper.value,
            status=StrategyRunStatus.pending.value,
            params={},
        ))
        await session.commit()
    await engine.dispose()
    return run_id


@pytest.mark.asyncio
async def test_runner_consumes_bars_and_writes_evaluate_events(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    db_path = tmp_path / "runner_skeleton.db"
    run_id = await _migrate_then_seed_run(db_path)

    bars = [_bar(i) for i in range(40)]
    broker = _StubBroker(bars)
    engine = _build_engine(db_path)

    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    await run_strategy(ctx)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        run = await session.scalar(select(StrategyRun).where(StrategyRun.id == run_id))
        assert run is not None
        assert run.status == "stopped"
        assert run.stopped_at is not None
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()

    kinds = [e.event_kind for e in events]
    assert "run_started" in kinds
    assert "run_stopped" in kinds
    evaluate_count = sum(1 for k in kinds if k == "evaluate")
    assert evaluate_count == 40, f"expected 40 evaluate events, got {evaluate_count}"


@pytest.mark.asyncio
async def test_runner_honors_cancel_event(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    db_path = tmp_path / "runner_cancel.db"
    run_id = await _migrate_then_seed_run(db_path)

    bars = [_bar(i) for i in range(200)]
    broker = _StubBroker(bars)
    engine = _build_engine(db_path)
    cancel = asyncio.Event()

    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=cancel,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.05)
        cancel.set()

    await asyncio.gather(run_strategy(ctx), _cancel_soon())

    async with AsyncSession(engine, expire_on_commit=False) as session:
        run = await session.scalar(select(StrategyRun).where(StrategyRun.id == run_id))
        assert run is not None
        assert run.status == "stopped"
    await engine.dispose()
