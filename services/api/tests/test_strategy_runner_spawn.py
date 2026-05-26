from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from app.db.models_market import Watchlist, WatchlistMember
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.db.session import session_factory
from app.services.strategy_runner_spawn import (
    spawn_contexts_from_watchlist,
)
from app.services.universe_resolver import EmptyUniverseError
from app.strategies.base import StrategyParams
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


class _NoopBroker:
    mode: Literal["paper", "live"] = "paper"

    async def get_quote(self, ticker: str) -> Quote:  # pragma: no cover - unused
        raise NotImplementedError

    async def get_positions(self) -> list[Position]:
        return []

    async def get_account(self) -> Account:  # pragma: no cover - unused
        raise NotImplementedError

    async def place_order(
        self, order: OrderRequest
    ) -> OrderResponse:  # pragma: no cover - unused
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> None:  # pragma: no cover
        return None

    async def list_orders(
        self, status: OrderStatusFilter = "all"
    ) -> list[Order]:  # pragma: no cover
        return []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:  # pragma: no cover
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
        async def _gen() -> AsyncIterator[Bar]:
            if False:
                yield
        return _gen()

    def stream_order_updates(self) -> AsyncIterator[Order]:
        async def _gen() -> AsyncIterator[Order]:
            if False:
                yield
        return _gen()


def _make_event_factory() -> asyncio.Event:
    return asyncio.Event()


def _empty_params() -> StrategyParams:
    return {}


@pytest.mark.asyncio
async def test_spawn_returns_one_context_per_member(
    db_session: AsyncSession,
    noop_judge_llm_client: object,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="manual")
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

    strategy = MacdRsiAdxStrategy()
    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        strategy=strategy,
        mode=StrategyRunMode.paper,
        params=_empty_params(),
        broker=_NoopBroker(),
        session_maker=session_factory,
        cancel_event_factory=_make_event_factory,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    assert [ctx.ticker for ctx in contexts] == ["SPY", "QQQ"]
    for ctx in contexts:
        assert ctx.strategy is strategy
        assert ctx.mode == "paper"
        assert ctx.broker is not None


@pytest.mark.asyncio
async def test_spawn_inserts_strategy_run_row_per_context(
    db_session: AsyncSession,
    noop_judge_llm_client: object,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="manual")
    db_session.add(watchlist)
    db_session.add(
        WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id,
            ticker="SPY",
            added_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db_session.commit()

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        strategy=MacdRsiAdxStrategy(),
        mode=StrategyRunMode.paper,
        params=_empty_params(),
        broker=_NoopBroker(),
        session_maker=session_factory,
        cancel_event_factory=_make_event_factory,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    run_ids = [ctx.run_id for ctx in contexts]
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(StrategyRun).where(StrategyRun.id.in_(run_ids))
            )
        ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == StrategyRunStatus.pending.value
    assert row.params == {"watchlist_id": str(watchlist.id)}


@pytest.mark.asyncio
async def test_spawn_emits_universe_resolved_event(
    db_session: AsyncSession,
    noop_judge_llm_client: object,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="manual")
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
        broker=_NoopBroker(),
        session_maker=session_factory,
        cancel_event_factory=_make_event_factory,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    run_ids = [ctx.run_id for ctx in contexts]
    async with session_factory() as session:
        events = (
            await session.execute(
                select(StrategyRunEvent)
                .where(StrategyRunEvent.run_id.in_(run_ids))
                .where(StrategyRunEvent.event_kind == "universe_resolved")
            )
        ).scalars().all()
    assert len(events) == len(contexts)
    for event in events:
        assert event.payload["watchlist_id"] == str(watchlist.id)
        assert event.payload["resolved_tickers"] == ["SPY", "QQQ"]


@pytest.mark.asyncio
async def test_spawn_against_empty_watchlist_raises(
    db_session: AsyncSession,
    noop_judge_llm_client: object,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="empty")
    db_session.add(watchlist)
    await db_session.commit()
    with pytest.raises(EmptyUniverseError):
        await spawn_contexts_from_watchlist(
            db_session,
            watchlist_id=watchlist.id,
            strategy=MacdRsiAdxStrategy(),
            mode=StrategyRunMode.paper,
            params=_empty_params(),
            broker=_NoopBroker(),
            session_maker=session_factory,
            cancel_event_factory=_make_event_factory,
            llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
        )
    async with session_factory() as session:
        runs = (
            await session.execute(
                select(StrategyRun).where(
                    StrategyRun.params["watchlist_id"].as_string() == str(watchlist.id)
                )
            )
        ).scalars().all()
    assert runs == []
