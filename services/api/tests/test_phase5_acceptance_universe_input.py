"""Phase 5 acceptance (spec §12 Phase 5).

Two scenarios:
  (a) Manual watchlist populated via the resolver -> spawn -> runners
      fire `evaluate` events for the resolved tickers.
  (b) Research-driven watchlist populated via `build_research_watchlist`
      from a seeded Hypothesis/Entity graph -> spawn -> runners fire
      `evaluate` events for the resolved tickers.

Acceptance bar: for each scenario, every ticker in the resolved set
gets at least one `evaluate` event AND each run has the
`universe_resolved` event with the correct `watchlist_id`.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import (
    Account,
    Bar,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatusFilter,
    Position,
    Quote,
    Timeframe,
    TradabilityCheck,
)
from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.db.models_strategy_runner import (
    StrategyRiskConfig,
    StrategyRunEvent,
    StrategyRunMode,
)
from app.db.session import session_factory
from app.services.research_watchlist_builder import build_research_watchlist
from app.services.strategy_runner import StrategyRunnerContext
from app.services.strategy_runner import run as run_strategy
from app.services.strategy_runner_spawn import spawn_contexts_from_watchlist
from app.strategies.base import StrategyParams
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy

_BAR_COUNT_PER_TICKER: int = 5
_RUNNER_GATHER_TIMEOUT_SECONDS: float = 10.0


def _empty_params() -> StrategyParams:
    return {}


class _DeterministicBroker:
    mode: Literal["paper", "live"] = "paper"

    def __init__(self) -> None:
        self._next_order_id = 1

    async def get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError

    async def get_positions(self) -> list[Position]:
        return []

    async def get_account(self) -> Account:
        raise NotImplementedError

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        broker_id = f"broker-{self._next_order_id}"
        self._next_order_id += 1
        return OrderResponse(
            broker_order_id=broker_id,
            client_order_id=order.client_order_id,
            status="filled",
            submitted_at=datetime.now(UTC),
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        return None

    async def list_orders(self, status: OrderStatusFilter = "all") -> list[Order]:
        return []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        return TradabilityCheck(
            ticker=ticker,
            is_tradable=True,
            is_shortable=True,
            is_halted=False,
            fractionable=True,
        )

    def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]:
        ticker = tickers[0]
        base = datetime(2026, 5, 21, 14, 30, tzinfo=UTC)
        bars: list[Bar] = []
        price = Decimal("400.00")
        for i in range(_BAR_COUNT_PER_TICKER):
            bars.append(
                Bar(
                    ticker=ticker,
                    timeframe=timeframe,
                    open=price,
                    high=price + Decimal("0.10"),
                    low=price - Decimal("0.10"),
                    close=price,
                    volume=Decimal("1000"),
                    vwap=None,
                    as_of=base + timedelta(minutes=i),
                )
            )

        async def _gen() -> AsyncIterator[Bar]:
            for bar in bars:
                yield bar

        return _gen()

    def stream_order_updates(self) -> AsyncIterator[Order]:
        async def _gen() -> AsyncIterator[Order]:
            if False:
                yield

        return _gen()


async def _seed_paper_risk_config(session: AsyncSession) -> None:
    existing = await session.scalar(
        select(StrategyRiskConfig).where(StrategyRiskConfig.mode == "paper")
    )
    if existing is not None:
        return
    session.add(
        StrategyRiskConfig(
            id=uuid.uuid4(),
            mode="paper",
            max_position_per_ticker_shares=Decimal("50"),
            max_position_per_ticker_notional_usd=Decimal("5000"),
            max_open_positions=6,
            max_daily_loss_usd=Decimal("1000"),
            max_consecutive_losses=5,
            daily_profit_target_usd=Decimal("2000"),
            max_orders_per_minute_per_ticker=3,
        )
    )
    await session.commit()


def _make_cancel_event() -> asyncio.Event:
    return asyncio.Event()


async def _drain_runners(contexts: list[StrategyRunnerContext]) -> None:
    tasks = [asyncio.create_task(run_strategy(ctx)) for ctx in contexts]
    await asyncio.wait_for(
        asyncio.gather(*tasks), timeout=_RUNNER_GATHER_TIMEOUT_SECONDS
    )


@pytest.mark.asyncio
async def test_phase5_acceptance_manual_watchlist_runner_consumes_correctly(
    db_session: AsyncSession,
) -> None:
    await _seed_paper_risk_config(db_session)

    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="manual phase5",
        source=WatchlistSource.manual.value,
    )
    db_session.add(watchlist)
    db_session.add(
        WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id,
            ticker="SPY",
            added_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id,
            ticker="QQQ",
            added_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await db_session.commit()

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        strategy=MacdRsiAdxStrategy(),
        mode=StrategyRunMode.paper,
        params=_empty_params(),
        broker=_DeterministicBroker(),
        session_maker=session_factory,
        cancel_event_factory=_make_cancel_event,
    )
    assert {ctx.ticker for ctx in contexts} == {"SPY", "QQQ"}

    await _drain_runners(contexts)

    async with session_factory() as session:
        run_ids = [ctx.run_id for ctx in contexts]
        universe_events = (
            await session.execute(
                select(StrategyRunEvent)
                .where(StrategyRunEvent.run_id.in_(run_ids))
                .where(StrategyRunEvent.event_kind == "universe_resolved")
            )
        ).scalars().all()
        assert len(universe_events) == 2
        for event in universe_events:
            assert event.payload["watchlist_id"] == str(watchlist.id)

        evaluate_events = (
            await session.execute(
                select(StrategyRunEvent)
                .where(StrategyRunEvent.run_id.in_(run_ids))
                .where(StrategyRunEvent.event_kind == "evaluate")
            )
        ).scalars().all()
        assert len(evaluate_events) >= 2

        seen_run_ids = {event.run_id for event in evaluate_events}
        assert seen_run_ids == set(run_ids)


@pytest.mark.asyncio
async def test_phase5_acceptance_research_driven_watchlist_runner_consumes_correctly(
    db_session: AsyncSession,
) -> None:
    await _seed_paper_risk_config(db_session)

    spy_entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.company.value,
        canonical_name="SPY",
        ticker_normalized="SPY",
    )
    qqq_entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.company.value,
        canonical_name="QQQ",
        ticker_normalized="QQQ",
    )
    db_session.add_all([spy_entity, qqq_entity])

    now = datetime.now(UTC)
    db_session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text="broad market resilient",
            scope_entity_ids=[str(spy_entity.id)],
            status=HypothesisStatus.active.value,
            belief=0.85,
            last_activity_at=now - timedelta(hours=1),
        )
    )
    db_session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text="tech outperforming",
            scope_entity_ids=[str(qqq_entity.id)],
            status=HypothesisStatus.active.value,
            belief=0.75,
            last_activity_at=now - timedelta(hours=2),
        )
    )

    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research phase5",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=10,
    )
    assert count == 2

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        strategy=MacdRsiAdxStrategy(),
        mode=StrategyRunMode.paper,
        params=_empty_params(),
        broker=_DeterministicBroker(),
        session_maker=session_factory,
        cancel_event_factory=_make_cancel_event,
    )
    assert {ctx.ticker for ctx in contexts} == {"SPY", "QQQ"}

    await _drain_runners(contexts)

    async with session_factory() as session:
        run_ids = [ctx.run_id for ctx in contexts]
        universe_events = (
            await session.execute(
                select(StrategyRunEvent)
                .where(StrategyRunEvent.run_id.in_(run_ids))
                .where(StrategyRunEvent.event_kind == "universe_resolved")
            )
        ).scalars().all()
        assert len(universe_events) == 2
        for event in universe_events:
            assert event.payload["watchlist_id"] == str(watchlist.id)

        evaluate_events = (
            await session.execute(
                select(StrategyRunEvent)
                .where(StrategyRunEvent.run_id.in_(run_ids))
                .where(StrategyRunEvent.event_kind == "evaluate")
            )
        ).scalars().all()
        assert len(evaluate_events) >= 2
        seen_run_ids = {event.run_id for event in evaluate_events}
        assert seen_run_ids == set(run_ids)
