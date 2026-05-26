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
from sqlalchemy import update as sa_update
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.brokers.base import (
    Bar,
    OrderRequest,
    OrderResponse,
    Position,
    TradabilityCheck,
)
from app.db.models_strategy_runner import (
    StrategyLiveOrder,
    StrategyRiskConfig,
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


class _AlwaysLongStrategy:
    """Test strategy that always wants to be long. Forces an entry order
    on the first bar."""

    key: str = "always_long"
    name: str = "Always Long"
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
        return StrategyResult(
            target=1,
            meta={"phase": "force-long"},
            size_hint=1,
            stop_pts=2.0,
        )


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


class _PaperBrokerStub:
    mode: str = "paper"
    placed_orders: list[OrderRequest]

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars
        self.placed_orders = []

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
        self.placed_orders.append(order)
        return OrderResponse(
            broker_order_id=f"stub-{len(self.placed_orders)}",
            client_order_id=order.client_order_id,
            status="filled",
            submitted_at=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
        )

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
async def test_runner_submits_order_through_full_gate_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "order_path.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="always_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    broker = _PaperBrokerStub([_bar(i) for i in range(3)])
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    assert len(broker.placed_orders) >= 1
    assert broker.placed_orders[0].ticker == "SPY"
    assert broker.placed_orders[0].side == "buy"
    assert broker.placed_orders[0].quantity == Decimal("1")

    async with AsyncSession(engine, expire_on_commit=False) as session:
        live_orders = (
            await session.scalars(
                select(StrategyLiveOrder).where(StrategyLiveOrder.run_id == run_id)
            )
        ).all()
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()

    assert len(live_orders) >= 1
    assert live_orders[0].broker_order_id == "stub-1"
    assert live_orders[0].status == "filled"

    kinds = [e.event_kind for e in events]
    assert "judge_verdict" in kinds
    assert "approval_decision" in kinds
    assert "order_submit" in kinds
    assert "order_fill" in kinds


@pytest.mark.asyncio
async def test_risk_reject_blocks_order_submission(tmp_path: Path) -> None:
    """Set max_position_per_ticker_shares=0 so every buy is rejected.
    Verify no broker.place_order calls happen and a `risk_reject` event
    is written."""
    db_path = tmp_path / "risk_reject.db"
    _migrate(db_path)
    engine = _build_engine(db_path)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(
            sa_update(StrategyRiskConfig)
            .where(StrategyRiskConfig.mode == "paper")
            .values(max_position_per_ticker_shares=0)
        )
        await session.commit()

    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="always_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    broker = _PaperBrokerStub([_bar(i) for i in range(3)])
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    assert len(broker.placed_orders) == 0
    async with AsyncSession(engine, expire_on_commit=False) as session:
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()
    kinds = [e.event_kind for e in events]
    assert "risk_reject" in kinds
    assert "order_submit" not in kinds
