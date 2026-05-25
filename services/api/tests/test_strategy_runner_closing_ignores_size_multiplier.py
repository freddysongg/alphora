from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.brokers.base import Bar, OrderRequest, OrderResponse, Position, TradabilityCheck
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_strategy_runner import (
    StrategyLiveOrder,
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


class _FlattenStrategy:
    """Strategy that always returns target=0 to force a closing order.

    When the runner starts with current_position > 0 (seeded in ctx), the
    strategy sees sign=1 but returns target=0 -> bias change -> close order.
    """

    key: str = "flatten_strategy"
    name: str = "Flatten Strategy"
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
        return StrategyResult(target=0, meta={}, size_hint=None, stop_pts=None)


def _bar(i: int) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal("105.0"),
        high=Decimal("105.5"),
        low=Decimal("104.5"),
        close=Decimal("105.0"),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=i),
    )


class _SubmittedBrokerStub:
    """Broker that always accepts orders with status=filled.

    Bug #3 is about qty calculation, not fill status, so we use filled
    here to keep trail-state / position updates clean and focus the
    assertion on the qty column.
    """

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


@dataclass
class _ApproveReducedJudgeLlmClient:
    """Judge LLM stub that returns approve_reduced with size_multiplier=0.5."""

    log_id: uuid.UUID = field(default_factory=uuid.uuid4)

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        prompt_version: str | None = None,
        stage: str | None = None,
        agent_name: str | None = None,
    ) -> LlmCompletionResult:
        session.add(
            LlmCallLog(
                id=self.log_id,
                model=model,
                prompt_hash="approve_reduced_stub",
                input_hash="approve_reduced_stub",
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.00"),
                latency_ms=1,
                status=LlmCallStatus.success,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
            )
        )
        await session.commit()
        return LlmCompletionResult(
            content=json.dumps({
                "decision": "approve_reduced",
                "reasoning_md": "reduce position size",
                "size_multiplier": 0.5,
            }),
            model=model,
            usage=TokenUsage(),
            cost_usd=Decimal("0.00"),
            latency_ms=1,
            log_id=self.log_id,
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
async def test_closing_order_ignores_judge_size_multiplier(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closing_multiplier.db"
    _migrate(db_path)
    engine = _build_engine(db_path)
    run_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="flatten_strategy",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={},
            )
        )
        await session.commit()

    broker = _SubmittedBrokerStub([_bar(0)])
    judge_client = _ApproveReducedJudgeLlmClient()
    ctx = StrategyRunnerContext(
        run_id=run_id,
        strategy=_FlattenStrategy(),
        ticker="SPY",
        mode="paper",
        params={},
        broker=broker,  # type: ignore[arg-type]
        session_maker=lambda: AsyncSession(engine, expire_on_commit=False),
        cancel_event=asyncio.Event(),
        llm_client=judge_client,  # type: ignore[arg-type]
        current_position=Decimal("10"),
    )
    await run_strategy(ctx)

    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].quantity == Decimal("10"), (
        f"expected full close qty=10, got {broker.placed_orders[0].quantity}"
    )

    async with AsyncSession(engine, expire_on_commit=False) as session:
        live_orders = (
            await session.scalars(
                select(StrategyLiveOrder).where(StrategyLiveOrder.run_id == run_id)
            )
        ).all()
    await engine.dispose()

    assert len(live_orders) == 1
    assert live_orders[0].qty == Decimal("10"), (
        f"strategy_live_orders.qty should be 10 (full close), got {live_orders[0].qty}"
    )
    assert ctx.current_position == Decimal("0")
    assert ctx.trail_state is None
