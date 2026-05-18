import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.models_paper import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    PaperPortfolio,
    PaperPosition,
)
from app.services.paper_filler import (
    FilledOutcome,
    PaperFiller,
    RejectedOutcome,
    SkippedOutcome,
)

_QUOTE_CENTS: int = 20_000


class FakeQuoteService:
    def __init__(self, quote_cents: int = _QUOTE_CENTS) -> None:
        self._quote_cents = quote_cents

    async def get_quote(self, ticker: str) -> int | None:
        if not ticker:
            return None
        return self._quote_cents


@pytest.fixture()
async def isolated_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _insert_portfolio(
    factory: async_sessionmaker[AsyncSession], *, cash_cents: int
) -> PaperPortfolio:
    portfolio = PaperPortfolio(
        id=uuid.uuid4(), name="Test", cash_cents=cash_cents
    )
    async with factory() as session:
        session.add(portfolio)
        await session.commit()
    return portfolio


async def _insert_order(
    factory: async_sessionmaker[AsyncSession],
    *,
    portfolio_id: uuid.UUID,
    side: OrderSide,
    ticker: str,
    quantity: int,
    status: OrderStatus = OrderStatus.pending,
) -> PaperOrder:
    order = PaperOrder(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        order_type=OrderType.market,
        status=status,
        submitted_at=datetime.now(UTC),
    )
    async with factory() as session:
        session.add(order)
        await session.commit()
    return order


async def _insert_position(
    factory: async_sessionmaker[AsyncSession],
    *,
    portfolio_id: uuid.UUID,
    ticker: str,
    quantity: int,
    avg_cost_cents: int,
) -> PaperPosition:
    position = PaperPosition(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        ticker=ticker,
        quantity=quantity,
        avg_cost_cents=avg_cost_cents,
        opened_at=datetime.now(UTC),
    )
    async with factory() as session:
        session.add(position)
        await session.commit()
    return position


async def _load_order(
    factory: async_sessionmaker[AsyncSession], order_id: uuid.UUID
) -> PaperOrder:
    async with factory() as session:
        stmt = select(PaperOrder).where(PaperOrder.id == order_id)
        return (await session.execute(stmt)).scalar_one()


async def _load_portfolio(
    factory: async_sessionmaker[AsyncSession], portfolio_id: uuid.UUID
) -> PaperPortfolio:
    async with factory() as session:
        stmt = select(PaperPortfolio).where(PaperPortfolio.id == portfolio_id)
        return (await session.execute(stmt)).scalar_one()


async def _load_open_position(
    factory: async_sessionmaker[AsyncSession],
    portfolio_id: uuid.UUID,
    ticker: str,
) -> PaperPosition | None:
    async with factory() as session:
        stmt = (
            select(PaperPosition)
            .where(PaperPosition.portfolio_id == portfolio_id)
            .where(PaperPosition.ticker == ticker)
            .where(PaperPosition.closed_at.is_(None))
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def test_buy_fill_decrements_cash_and_creates_position(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=1_000_000)
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.buy,
        ticker="AAPL",
        quantity=10,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.filled == 1
    assert result.rejected == 0
    assert result.skipped == 0
    assert result.errors == []
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.filled
    assert stored_order.filled_price_cents == _QUOTE_CENTS
    assert stored_order.filled_at is not None
    stored_portfolio = await _load_portfolio(isolated_session_factory, portfolio.id)
    assert stored_portfolio.cash_cents == 1_000_000 - _QUOTE_CENTS * 10
    position = await _load_open_position(
        isolated_session_factory, portfolio.id, "AAPL"
    )
    assert position is not None
    assert position.quantity == 10
    assert position.avg_cost_cents == _QUOTE_CENTS


async def test_sell_fill_increments_cash_and_decrements_position(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=500_000)
    await _insert_position(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        quantity=10,
        avg_cost_cents=15_000,
    )
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.sell,
        ticker="AAPL",
        quantity=4,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.filled == 1
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.filled
    stored_portfolio = await _load_portfolio(isolated_session_factory, portfolio.id)
    assert stored_portfolio.cash_cents == 500_000 + _QUOTE_CENTS * 4
    position = await _load_open_position(
        isolated_session_factory, portfolio.id, "AAPL"
    )
    assert position is not None
    assert position.quantity == 6
    assert position.closed_at is None


async def test_buy_rejected_for_insufficient_cash(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=1_000)
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.buy,
        ticker="AAPL",
        quantity=10,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.rejected == 1
    assert result.filled == 0
    assert isinstance(result.outcomes[0], RejectedOutcome)
    assert "insufficient cash" in result.outcomes[0].reason
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.rejected
    stored_portfolio = await _load_portfolio(isolated_session_factory, portfolio.id)
    assert stored_portfolio.cash_cents == 1_000


async def test_sell_rejected_for_missing_position(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=500_000)
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.sell,
        ticker="AAPL",
        quantity=4,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.rejected == 1
    assert isinstance(result.outcomes[0], RejectedOutcome)
    assert "no open position" in result.outcomes[0].reason
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.rejected


async def test_sell_rejected_for_insufficient_shares(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=500_000)
    await _insert_position(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        quantity=3,
        avg_cost_cents=15_000,
    )
    await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.sell,
        ticker="AAPL",
        quantity=5,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.rejected == 1
    assert isinstance(result.outcomes[0], RejectedOutcome)
    assert "insufficient shares" in result.outcomes[0].reason


async def test_cancelled_order_between_selection_and_lock_is_skipped(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=1_000_000)
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.buy,
        ticker="AAPL",
        quantity=10,
    )

    async with isolated_session_factory() as session:
        stmt = select(PaperOrder).where(PaperOrder.id == order.id)
        loaded = (await session.execute(stmt)).scalar_one()
        loaded.status = OrderStatus.cancelled
        await session.commit()

    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )
    result = await filler.fill_open_orders()

    assert result.filled == 0
    assert result.rejected == 0
    assert result.skipped == 0
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.cancelled


async def test_buy_into_existing_position_recomputes_average_cost(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=10_000_000)
    await _insert_position(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        quantity=10,
        avg_cost_cents=10_000,
    )
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.buy,
        ticker="AAPL",
        quantity=10,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory,
        quote_service=FakeQuoteService(quote_cents=30_000),
    )

    result = await filler.fill_open_orders()

    assert result.filled == 1
    assert isinstance(result.outcomes[0], FilledOutcome)
    position = await _load_open_position(
        isolated_session_factory, portfolio.id, "AAPL"
    )
    assert position is not None
    assert position.quantity == 20
    assert position.avg_cost_cents == 20_000
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.filled_price_cents == 30_000


async def test_sell_to_zero_closes_position(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=500_000)
    await _insert_position(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        quantity=10,
        avg_cost_cents=15_000,
    )
    await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.sell,
        ticker="AAPL",
        quantity=10,
    )
    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=FakeQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.filled == 1
    open_position = await _load_open_position(
        isolated_session_factory, portfolio.id, "AAPL"
    )
    assert open_position is None


async def test_skipped_when_quote_unavailable(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    portfolio = await _insert_portfolio(isolated_session_factory, cash_cents=1_000_000)
    order = await _insert_order(
        isolated_session_factory,
        portfolio_id=portfolio.id,
        side=OrderSide.buy,
        ticker="AAPL",
        quantity=10,
    )

    class NoQuoteService:
        async def get_quote(self, ticker: str) -> int | None:
            return None

    filler = PaperFiller(
        session_factory=isolated_session_factory, quote_service=NoQuoteService()
    )

    result = await filler.fill_open_orders()

    assert result.skipped == 1
    assert result.filled == 0
    stored_order = await _load_order(isolated_session_factory, order.id)
    assert stored_order.status == OrderStatus.pending
    assert isinstance(result.outcomes[0], SkippedOutcome)
