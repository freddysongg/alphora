"""Phase 4 acceptance (spec section 12 Phase 4).

Gated on ALPACA_INTEGRATION=1 + ALPACA_API_KEY + ALPACA_API_SECRET +
ALPACA_MODE=paper. Without those env vars the test skips with a clear
message -- CI defaults to skip.

The test:
1. Creates a `strategy_runs` row for MacdRsiAdxStrategy on SPY (paper).
2. Spawns the runner against the live AlpacaAdapter (stream_bars).
3. Waits up to ALPACA_PAPER_RUNNER_DURATION_S (default 300s).
4. Sets cancel_event to wind down cleanly.
5. Asserts: run reached `stopped`; at least 1 evaluate event in the
   window; if duration_s >= 1800, at least 1 live_orders row.

The acceptance bar is `runner ran without errors and produced an audit
trail`, not `runner made money`. Strategy backtest acceptance is
covered by Phase 2/3.

Known issue (Phase 4c followup): alpaca-py's StockDataStream.run() and
TradingStream.run() are sync methods. The Task 20/21 unit tests use
AsyncMock so they pass with `asyncio.create_task(stream.run())`. Real
integration will likely error here -- this test surfacing the issue is
the right place to validate the fix. The fix is either calling
`stream._run_forever()` directly or wrapping `stream.run()` in
`asyncio.to_thread`. Document the actual error encountered in a Phase
4 follow-up note if reached.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.brokers.alpaca import AlpacaAdapter
from app.db.models_strategy_runner import (
    StrategyLiveOrder,
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy

_REQUIRED_ENV: tuple[str, ...] = (
    "ALPACA_INTEGRATION",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
)
_DEFAULT_DURATION_S: int = 300
_LONG_RUN_ORDER_THRESHOLD_S: int = 1800


def _skip_if_no_creds() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(
            f"Phase 4 acceptance requires {_REQUIRED_ENV}; missing={missing}. "
            "Set ALPACA_INTEGRATION=1, ALPACA_API_KEY, ALPACA_API_SECRET, and "
            "ALPACA_MODE=paper to run this test against the Alpaca paper sandbox."
        )
    alpaca_mode = os.environ.get("ALPACA_MODE", "paper")
    if alpaca_mode != "paper":
        pytest.skip(
            "Phase 4 acceptance must run against ALPACA_MODE=paper; "
            f"got ALPACA_MODE={alpaca_mode!r}"
        )


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
async def test_phase4_acceptance_alpaca_paper_runner(tmp_path: Path) -> None:
    _skip_if_no_creds()

    duration_s = int(
        os.environ.get("ALPACA_PAPER_RUNNER_DURATION_S", str(_DEFAULT_DURATION_S))
    )
    db_path = tmp_path / "phase4_acceptance.db"
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

    adapter = AlpacaAdapter.from_env()
    assert adapter.mode == "paper"

    cancel = asyncio.Event()
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        mode="paper",
        params={"adx_min": 25.0},
        broker=adapter,
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=cancel,
    )

    started = datetime.now(UTC)

    async def _cancel_after() -> None:
        await asyncio.sleep(duration_s)
        cancel.set()

    await asyncio.gather(run_strategy(ctx), _cancel_after())

    elapsed = (datetime.now(UTC) - started).total_seconds()
    print(f"phase 4 acceptance: runner ran for {elapsed:.1f}s")

    async with AsyncSession(engine, expire_on_commit=False) as session:
        run = await session.scalar(select(StrategyRun).where(StrategyRun.id == run_id))
        events = (
            await session.scalars(
                select(StrategyRunEvent).where(StrategyRunEvent.run_id == run_id)
            )
        ).all()
        live_orders = (
            await session.scalars(
                select(StrategyLiveOrder).where(StrategyLiveOrder.run_id == run_id)
            )
        ).all()
    await engine.dispose()

    assert run is not None
    assert run.status == StrategyRunStatus.stopped.value, (
        f"expected stopped, got {run.status!r} error={run.error_msg!r}"
    )
    evaluate_count = sum(1 for e in events if e.event_kind == "evaluate")
    assert evaluate_count >= 1, (
        f"expected at least 1 evaluate event in {duration_s}s window; "
        f"got 0. Is the market open? Total events: {len(events)}, "
        f"kinds: {sorted({e.event_kind for e in events})}"
    )
    if duration_s >= _LONG_RUN_ORDER_THRESHOLD_S:
        assert len(live_orders) >= 1, (
            "expected at least 1 order in a >=30min window; "
            f"got 0. orders submitted: {[o.broker_order_id for o in live_orders]}"
        )
