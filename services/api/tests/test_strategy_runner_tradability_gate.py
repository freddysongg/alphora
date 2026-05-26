"""Regression coverage for the runner's tradability gate (spec §8.3 step 1).

`_submit_via_gates` MUST consult `BrokerAdapter.is_tradable` before any
risk-cap evaluation. Halted symbols, delisted symbols, and short-open
attempts on non-shortable assets must be rejected without reaching the
broker. Closing orders on halted symbols are ALSO rejected (halted means
no trading at all). Closing a short (a buy) is NOT blocked by
non-shortable status.
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
from sqlalchemy import event, select
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
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


class _AlwaysLongStrategy:
    """Test strategy that always wants to be long."""

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


class _AlwaysShortStrategy:
    """Test strategy that always wants to be short."""

    key: str = "always_short"
    name: str = "Always Short"
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
            target=-1,
            meta={"phase": "force-short"},
            size_hint=1,
            stop_pts=2.0,
        )


class _AlwaysFlatStrategy:
    """Test strategy that always wants to be flat (target=0)."""

    key: str = "always_flat"
    name: str = "Always Flat"
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
            target=0,
            meta={"phase": "force-flat"},
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


class _TradabilityStubBroker:
    """Yields a fixed sequence of bars and a configurable TradabilityCheck."""

    mode: str = "paper"
    placed_orders: list[OrderRequest]

    def __init__(
        self,
        bars: list[Bar],
        tradability: TradabilityCheck,
        existing: Position | None = None,
    ) -> None:
        self._bars = bars
        self._tradability = tradability
        self._existing = existing
        self.placed_orders = []

    async def get_positions(self) -> list[Position]:
        return [self._existing] if self._existing is not None else []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        del ticker
        return self._tradability

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


async def _collect_orders_and_events(
    engine: AsyncEngine, run_id: uuid.UUID
) -> tuple[list[StrategyLiveOrder], list[StrategyRunEvent]]:
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
    return list(live_orders), list(events)


@pytest.mark.asyncio
async def test_runner_blocks_open_on_halted_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "halted_open.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_long")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=True,
            is_shortable=True,
            is_halted=True,
            fractionable=True,
        ),
    )
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

    live_orders, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    assert broker.placed_orders == []
    assert live_orders == []
    blocks = [
        e for e in events
        if e.event_kind == "not_tradable" and e.payload.get("reason") == "halted"
    ]
    assert len(blocks) >= 1
    assert blocks[0].payload["ticker"] == "SPY"
    assert blocks[0].payload["side"] == "buy"
    assert blocks[0].level == "warn"


@pytest.mark.asyncio
async def test_runner_blocks_close_on_halted_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "halted_close.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_flat")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=True,
            is_shortable=True,
            is_halted=True,
            fractionable=True,
        ),
        existing=Position(
            ticker="SPY",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("100"),
        ),
    )
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysFlatStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    live_orders, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    assert broker.placed_orders == []
    assert live_orders == []
    blocks = [
        e for e in events
        if e.event_kind == "not_tradable" and e.payload.get("reason") == "halted"
    ]
    assert len(blocks) >= 1
    assert blocks[0].payload["side"] == "sell"


@pytest.mark.asyncio
async def test_runner_blocks_open_when_is_tradable_false(tmp_path: Path) -> None:
    db_path = tmp_path / "not_tradable.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_long")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=False,
            is_shortable=False,
            is_halted=False,
            fractionable=True,
        ),
    )
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

    live_orders, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    assert broker.placed_orders == []
    assert live_orders == []
    blocks = [
        e for e in events
        if e.event_kind == "not_tradable" and e.payload.get("reason") == "not_tradable"
    ]
    assert len(blocks) >= 1


@pytest.mark.asyncio
async def test_runner_blocks_short_open_when_not_shortable(tmp_path: Path) -> None:
    db_path = tmp_path / "not_shortable.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_short")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=True,
            is_shortable=False,
            is_halted=False,
            fractionable=True,
        ),
    )
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysShortStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    live_orders, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    assert broker.placed_orders == []
    assert live_orders == []
    blocks = [
        e for e in events
        if e.event_kind == "not_tradable" and e.payload.get("reason") == "not_shortable"
    ]
    assert len(blocks) >= 1
    assert blocks[0].payload["side"] == "sell"


@pytest.mark.asyncio
async def test_runner_allows_long_close_even_when_not_shortable(tmp_path: Path) -> None:
    """Closing a short position is a BUY, not a sell, so the not_shortable
    flag must not block it."""
    db_path = tmp_path / "close_short_ok.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_flat")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=True,
            is_shortable=False,
            is_halted=False,
            fractionable=True,
        ),
        existing=Position(
            ticker="SPY",
            quantity=Decimal("-5"),
            avg_entry_price=Decimal("100"),
        ),
    )
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_AlwaysFlatStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    _, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    blocks = [e for e in events if e.event_kind == "not_tradable"]
    assert blocks == [], (
        "tradability gate must not block a buy that closes a short, even "
        f"when is_shortable=False; saw events: {[e.payload for e in blocks]}"
    )


@pytest.mark.asyncio
async def test_runner_allows_order_when_fully_tradable(tmp_path: Path) -> None:
    db_path = tmp_path / "fully_tradable.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = await _seed_run(engine, "always_long")

    broker = _TradabilityStubBroker(
        bars=[_bar(i) for i in range(3)],
        tradability=TradabilityCheck(
            ticker="SPY",
            is_tradable=True,
            is_shortable=True,
            is_halted=False,
            fractionable=True,
        ),
    )
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

    live_orders, events = await _collect_orders_and_events(engine, run_id)
    await engine.dispose()

    assert len(broker.placed_orders) >= 1
    assert broker.placed_orders[0].side == "buy"
    assert len(live_orders) >= 1
    blocks = [e for e in events if e.event_kind == "not_tradable"]
    assert blocks == []
