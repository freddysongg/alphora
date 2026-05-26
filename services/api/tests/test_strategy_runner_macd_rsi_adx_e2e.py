"""Phase 4b internal acceptance test (Task 19).

Exercises the real `MacdRsiAdxStrategy` against the Phase 2 SPY 30-day
1-minute fixture through a price-following stub broker. Validates that
the full runner stack (indicator window, risk caps, judge stub,
approval stub, broker mirror, trail manager, EOD flatten, same-bar
re-entry guard) processes ~11k bars without error and produces a
coherent audit trail.

Acceptance bar is "runner ran without errors and produced an audit
trail", not "runner made money" or "runner ended flat". The 30-day
fixture may end mid-session, so the flat-at-end check is gated on the
last bar landing on the EOD flatten minute (`RTH_CLOSE_ET_MIN - 1`).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from app.services.market_clock import RTH_CLOSE_ET_MIN, et_minutes
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Timeframe
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy

_FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
_FIXTURE_FILENAME: str = "spy_30day_1min.json"
_MIN_FIXTURE_BARS: int = 100
_MIN_EXPECTED_ORDERS: int = 2
_REQUIRED_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "run_started",
        "evaluate",
        "judge_verdict",
        "approval_decision",
        "order_submit",
        "order_fill",
        "run_stopped",
    }
)


def _load_spy_bars() -> list[Bar]:
    path = _FIXTURES_DIR / _FIXTURE_FILENAME
    if not path.exists():
        pytest.skip(
            f"SPY fixture missing at {path}; Phase 2 prerequisite not satisfied"
        )
    raw = json.loads(path.read_text())
    bars: list[Bar] = []
    for row in raw:
        ts = datetime.fromtimestamp(int(row["t"]) / 1000.0, tz=UTC)
        bars.append(
            Bar(
                ticker="SPY",
                timeframe="1min",
                open=Decimal(str(row["o"])),
                high=Decimal(str(row["h"])),
                low=Decimal(str(row["l"])),
                close=Decimal(str(row["c"])),
                volume=Decimal(str(row["v"])),
                vwap=None,
                as_of=ts,
            )
        )
    return bars


class _PriceFollowingBroker:
    """Stub broker that fills market orders at the most recent bar's close.

    Tracks an in-memory position so `get_positions` stays consistent with
    what the runner has submitted. The runner only queries positions
    during startup (position adoption); this broker returns flat there
    so the run starts clean.
    """

    mode: str = "paper"

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars
        self.placed_orders: list[OrderRequest] = []
        self._position: Decimal = Decimal("0")
        self._avg_entry: Decimal = Decimal("0")
        self._latest_close: Decimal = bars[0].close if bars else Decimal("0")

    async def get_positions(self) -> list[Position]:
        if self._position == 0:
            return []
        return [
            Position(
                ticker="SPY",
                quantity=self._position,
                avg_entry_price=self._avg_entry,
            )
        ]

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
        fill = self._latest_close
        delta = order.quantity if order.side == "buy" else -order.quantity
        if self._position == 0:
            self._avg_entry = fill
        self._position += delta
        return OrderResponse(
            broker_order_id=f"e2e-{len(self.placed_orders)}",
            client_order_id=order.client_order_id,
            status="filled",
            submitted_at=datetime.now(UTC),
        )

    def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]:
        del tickers, timeframe
        broker_self = self

        async def _gen() -> AsyncIterator[Bar]:
            for next_bar in broker_self._bars:
                broker_self._latest_close = next_bar.close
                yield next_bar

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
async def test_macd_rsi_adx_runner_e2e_against_stub_broker(
    tmp_path: Path,
    noop_judge_llm_client: object,
) -> None:
    bars = _load_spy_bars()
    if len(bars) < _MIN_FIXTURE_BARS:
        pytest.skip(f"SPY fixture too small ({len(bars)} bars)")

    db_path = tmp_path / "e2e.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={"adx_min": 25.0},
            )
        )
        await session.commit()

    broker = _PriceFollowingBroker(bars)
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        mode="paper",
        params={"adx_min": 25.0},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    await run_strategy(ctx)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        run = await session.scalar(
            select(StrategyRun).where(StrategyRun.id == run_id)
        )
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

    assert run is not None
    assert run.status == StrategyRunStatus.stopped.value
    assert len(live_orders) >= _MIN_EXPECTED_ORDERS, (
        f"expected >={_MIN_EXPECTED_ORDERS} orders, got {len(live_orders)}"
    )
    fills = [o for o in live_orders if o.status == "filled"]
    assert len(fills) >= _MIN_EXPECTED_ORDERS, (
        f"expected >={_MIN_EXPECTED_ORDERS} fills, got {len(fills)}"
    )

    kinds = {e.event_kind for e in events}
    missing = _REQUIRED_EVENT_KINDS - kinds
    assert not missing, f"missing required event kinds: {missing}"

    last_bar_is_eod = et_minutes(bars[-1].as_of) == RTH_CLOSE_ET_MIN - 1
    if last_bar_is_eod:
        assert ctx.current_position == Decimal("0"), (
            "EOD flatten should have closed the position on the final RTH bar"
        )
