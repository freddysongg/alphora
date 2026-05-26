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
    StrategyLiveOrder,
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


class _AlwaysLongStrategy:
    """Always returns target=1 so the runner fires a long entry on the first bar."""

    key: str = "always_long_submitted"
    name: str = "Always Long Submitted"
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
        return StrategyResult(target=1, meta={}, size_hint=5, stop_pts=None)


def _bar(i: int) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal("100.0"),
        high=Decimal("100.5"),
        low=Decimal("99.5"),
        close=Decimal("100.0"),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=i),
    )


class _SubmittedBrokerStub:
    """Broker whose place_order always returns status='submitted' (not filled)."""

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
            broker_order_id=f"stub-broker-{len(self.placed_orders)}",
            client_order_id=order.client_order_id,
            status="new",
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
async def test_position_updated_optimistically_when_market_order_submitted(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    """A market order that comes back 'submitted' (not yet filled) must still
    advance ctx.current_position so the next bar doesn't re-enter the same
    signal. The persisted live-order row must stay status='submitted' with
    filled_qty=0, and no order_fill event should be emitted."""
    db_path = tmp_path / "optimistic_submitted.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="always_long_submitted",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    broker = _SubmittedBrokerStub([_bar(0), _bar(1)])
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    await run_strategy(ctx)

    assert ctx.current_position == Decimal("5"), (
        f"expected optimistic position=5, got {ctx.current_position}"
    )
    assert len(broker.placed_orders) == 1, (
        f"expected exactly 1 order (no duplicate on bar 2), got {len(broker.placed_orders)}"
    )
    # Trail state must stay None on the optimistic path: there is no confirmed
    # fill price, so seeding TrailState would produce wrong stop levels.
    # Phase 6+ stream_order_updates reconciliation will initialize the trail
    # with the real avg_fill_price once the broker reports it.
    assert ctx.trail_state is None, (
        f"trail_state must stay None on optimistic fill (no confirmed fill price); "
        f"got {ctx.trail_state!r}"
    )

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

    assert len(live_orders) == 1
    assert live_orders[0].status == "submitted", (
        f"live order status should stay 'submitted', got {live_orders[0].status!r}"
    )
    assert live_orders[0].filled_qty == Decimal("0"), (
        f"filled_qty should be 0 for a submitted order, got {live_orders[0].filled_qty}"
    )

    fill_events = [e for e in events if e.event_kind == "order_fill"]
    assert len(fill_events) == 0, (
        f"no order_fill event should fire for optimistic path, got {fill_events}"
    )
