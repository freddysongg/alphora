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


class _OpenOnceLongStrategy:
    """Emit target=1 on every bar (with stop_pts + meta thresholds).

    Once long, target=1 == current_sign, so no additional entry orders
    fire — the trail manager is the only thing that can close the
    position.
    """

    key: str = "open_once_long"
    name: str = "Open Once Long"
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
                "break_even_pts": 1.0,
                "trail_trigger_pts": 1.5,
                "trail_distance_pts": 0.5,
            },
            size_hint=1,
            stop_pts=2.0,
            trail=TrailSpec(atr_multiplier=0.5, atr_period=14),
        )


def _bar(
    i: int,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal(str(close)),
        high=Decimal(str(high if high is not None else close + 0.1)),
        low=Decimal(str(low if low is not None else close - 0.1)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=i),
    )


class _ScriptedBroker:
    mode: str = "paper"
    placed_orders: list[OrderRequest]

    def __init__(self, bars: list[Bar], entry_fill: Decimal) -> None:
        self._bars = bars
        self.placed_orders = []
        self._entry_fill = entry_fill

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
        order_id = f"stub-{len(self.placed_orders)}"
        return OrderResponse(
            broker_order_id=order_id,
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
async def test_trail_exit_on_long_after_promotion(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    """Enter long at bar 0, watch trail state evolve through break-even
    and trailing modes, then exit when a subsequent bar's low pierces
    the tightened stop."""
    db_path = tmp_path / "trail_exit.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="open_once_long",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    bars = [
        _bar(0, close=100.0, high=100.2, low=99.9),
        _bar(1, close=100.5, high=100.8, low=100.3),
        _bar(2, close=101.5, high=101.5, low=101.0),
        _bar(3, close=99.5, high=100.5, low=99.5),
    ]
    broker = _ScriptedBroker(bars, entry_fill=Decimal("100.0"))
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_OpenOnceLongStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    await run_strategy(ctx)

    sides = [o.side for o in broker.placed_orders]
    assert "buy" in sides, f"expected entry buy, got {sides}"
    assert "sell" in sides, f"expected trail exit sell, got {sides}"

    async with AsyncSession(engine, expire_on_commit=False) as session:
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
    await engine.dispose()
    kinds = [e.event_kind for e in events]
    assert "stop_hit" in kinds
    assert ctx.current_position == Decimal("0")
    assert ctx.trail_state is None
    assert ctx.last_exit_bar_ts is not None
