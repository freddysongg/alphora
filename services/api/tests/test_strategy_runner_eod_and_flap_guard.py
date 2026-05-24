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
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe, TrailSpec


def _rth_bar(et_min: int, close: float = 100.0, day_offset: int = 0) -> Bar:
    """Build a bar at a specific ET minute-of-day. 09:30 ET = 13:30 UTC during EDT."""
    base = datetime(2026, 6, 15 + day_offset, 13, 30, tzinfo=UTC)
    offset_min = et_min - (9 * 60 + 30)
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal(str(close)),
        high=Decimal(str(close + 0.1)),
        low=Decimal(str(close - 0.1)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        vwap=None,
        as_of=base + timedelta(minutes=offset_min),
    )


class _RthLongStrategy:
    key: str = "rth_long"
    name: str = "RTH Long"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = True

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        del primary_bars, secondary_bars, current_position, params
        return StrategyResult(target=1, meta={}, size_hint=1)


class _OvernightLongStrategy:
    key: str = "overnight_long"
    name: str = "Overnight Long"
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
        return StrategyResult(target=1, meta={}, size_hint=1)


class _ExitViaTrailButStrategyWantsLong:
    """Strategy that always wants long, with trail thresholds tight enough
    that the trail manager will fire an exit on a pullback bar."""

    key: str = "trail_exit_strategy_long"
    name: str = "Trail Exit, Strategy Long"
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
            meta={
                "break_even_pts": 0.5,
                "trail_trigger_pts": 0.5,
                "trail_distance_pts": 0.05,
            },
            size_hint=1,
            stop_pts=0.1,
            trail=TrailSpec(atr_multiplier=0.5, atr_period=14),
        )


class _ScriptedBroker:
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
            broker_order_id=f"o-{len(self.placed_orders)}",
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
async def test_eod_flatten_on_requires_rth_strategy(tmp_path: Path) -> None:
    db_path = tmp_path / "eod.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="rth_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    bars = [
        _rth_bar(et_min=9 * 60 + 30),
        _rth_bar(et_min=15 * 60 + 58),
        _rth_bar(et_min=15 * 60 + 59),
    ]
    broker = _ScriptedBroker(bars)
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_RthLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)

    sides = [o.side for o in broker.placed_orders]
    assert sides == ["buy", "sell"], f"expected buy+sell flatten, got {sides}"
    assert ctx.current_position == Decimal("0")

    async with AsyncSession(engine, expire_on_commit=False) as session:
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()
    kinds = [e.event_kind for e in events]
    assert "eod_flatten" in kinds


@pytest.mark.asyncio
async def test_no_eod_flatten_when_strategy_is_not_requires_rth(
    tmp_path: Path,
) -> None:
    """An overnight-holding strategy must NOT be force-closed by EOD logic."""
    db_path = tmp_path / "no_eod.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="overnight_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    bars = [
        _rth_bar(et_min=9 * 60 + 30),
        _rth_bar(et_min=15 * 60 + 59),
    ]
    broker = _ScriptedBroker(bars)
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_OvernightLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)
    sides = [o.side for o in broker.placed_orders]
    assert sides == ["buy"], f"expected only entry, got {sides}"
    assert ctx.current_position == Decimal("1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_flap_guard_blocks_re_entry_on_exact_same_bar(
    tmp_path: Path,
) -> None:
    """When trail-manager exit fires AND strategy.evaluate returns target=1
    on the same bar, the runner must NOT submit both an exit and an entry.
    The early-return after trail exit is the primary mechanism; the explicit
    `last_exit_bar_ts` guard catches the same condition on subsequent paths.
    """
    db_path = tmp_path / "trail_flap.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="trail_exit_strategy_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    bars = [
        _rth_bar(et_min=9 * 60 + 30, close=100.0),
        Bar(
            ticker="SPY",
            timeframe="1min",
            open=Decimal("100.0"),
            high=Decimal("100.8"),
            low=Decimal("100.0"),
            close=Decimal("100.6"),
            volume=Decimal("1000"),
            vwap=None,
            as_of=datetime(2026, 6, 15, 13, 31, tzinfo=UTC),
        ),
        Bar(
            ticker="SPY",
            timeframe="1min",
            open=Decimal("100.6"),
            high=Decimal("100.85"),
            low=Decimal("100.55"),
            close=Decimal("100.7"),
            volume=Decimal("1000"),
            vwap=None,
            as_of=datetime(2026, 6, 15, 13, 32, tzinfo=UTC),
        ),
        Bar(
            ticker="SPY",
            timeframe="1min",
            open=Decimal("100.7"),
            high=Decimal("100.75"),
            low=Decimal("100.5"),
            close=Decimal("100.5"),
            volume=Decimal("1000"),
            vwap=None,
            as_of=datetime(2026, 6, 15, 13, 33, tzinfo=UTC),
        ),
    ]
    broker = _ScriptedBroker(bars)
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_ExitViaTrailButStrategyWantsLong(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
    )
    await run_strategy(ctx)
    sides = [o.side for o in broker.placed_orders]
    assert sides == ["buy", "sell"], f"flap guard failed: {sides}"
    await engine.dispose()
