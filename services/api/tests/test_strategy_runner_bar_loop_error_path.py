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

from app.brokers.base import Bar, OrderRequest, OrderResponse, Position, TradabilityCheck
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


class _RaisingStrategy:
    """Strategy whose evaluate() always raises to simulate a bar processing failure."""

    key: str = "raising_strategy"
    name: str = "Raising Strategy"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = False

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        del primary_bars, secondary_bars, current_position, params
        raise RuntimeError("simulated bar processing failure")


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


class _FlatBrokerStub:
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
            reason=None,
        )

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        raise AssertionError("place_order should not be called in this test")

    def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]:
        del tickers, timeframe

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


@pytest.mark.asyncio
async def test_runner_marks_errored_when_process_bar_raises(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    db_path = tmp_path / "bar_loop_error.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="raising_strategy",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    broker = _FlatBrokerStub([_bar(0)])
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_RaisingStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="simulated bar processing failure"):
        await run_strategy(ctx)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        run_row = await session.scalar(
            select(StrategyRun).where(StrategyRun.id == run_id)
        )
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()

    assert run_row is not None
    assert run_row.status == StrategyRunStatus.errored.value

    stopped_events = [e for e in events if e.event_kind == "run_stopped"]
    assert len(stopped_events) == 1
    assert stopped_events[0].payload.get("reason") == "bar_processing_failed"
    assert "simulated bar processing failure" in str(
        stopped_events[0].payload.get("error", "")
    )
    assert stopped_events[0].level == "error"
