import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_paper import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    PaperPortfolio,
    PaperPosition,
)
from app.logging import get_logger
from app.services.quote_service import QuoteService

_logger = get_logger(__name__)


@dataclass(frozen=True)
class FilledOutcome:
    kind: Literal["filled"]
    order_id: uuid.UUID
    fill_price_cents: int


@dataclass(frozen=True)
class RejectedOutcome:
    kind: Literal["rejected"]
    order_id: uuid.UUID
    reason: str


@dataclass(frozen=True)
class SkippedOutcome:
    kind: Literal["skipped"]
    order_id: uuid.UUID
    reason: str


FillOutcome = FilledOutcome | RejectedOutcome | SkippedOutcome


@dataclass(frozen=True)
class FillResult:
    filled: int = 0
    rejected: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    outcomes: list[FillOutcome] = field(default_factory=list)


class PaperFiller:
    """Fills pending market orders against a stub quote service.

    Each order is processed inside its own transaction with row-level locks
    on the order and portfolio so concurrent schedulers cannot double-fill.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        quote_service: QuoteService,
    ) -> None:
        self._session_factory = session_factory
        self._quote_service = quote_service

    async def fill_open_orders(self) -> FillResult:
        candidate_ids = await self._select_candidate_order_ids()
        filled_count = 0
        rejected_count = 0
        skipped_count = 0
        errors: list[str] = []
        outcomes: list[FillOutcome] = []
        for order_id in candidate_ids:
            try:
                outcome = await self._process_one(order_id)
            except Exception as exc:
                errors.append(f"order {order_id}: {exc}")
                _logger.exception(
                    "paper_filler_order_failed", order_id=str(order_id), error=str(exc)
                )
                continue
            outcomes.append(outcome)
            if isinstance(outcome, FilledOutcome):
                filled_count += 1
            elif isinstance(outcome, RejectedOutcome):
                rejected_count += 1
            else:
                skipped_count += 1
        return FillResult(
            filled=filled_count,
            rejected=rejected_count,
            skipped=skipped_count,
            errors=errors,
            outcomes=outcomes,
        )

    async def _select_candidate_order_ids(self) -> list[uuid.UUID]:
        async with self._session_factory() as session:
            stmt = (
                select(PaperOrder.id)
                .where(PaperOrder.status.in_([OrderStatus.pending, OrderStatus.accepted]))
                .where(PaperOrder.order_type == OrderType.market)
                .order_by(PaperOrder.submitted_at.asc())
            )
            rows = await session.execute(stmt)
            return [row[0] for row in rows.all()]

    async def _process_one(self, order_id: uuid.UUID) -> FillOutcome:
        async with self._session_factory() as session:
            order = await self._lock_order(session, order_id)
            if order is None:
                return SkippedOutcome(
                    kind="skipped", order_id=order_id, reason="order disappeared"
                )
            if order.status not in {OrderStatus.pending, OrderStatus.accepted}:
                return SkippedOutcome(
                    kind="skipped",
                    order_id=order_id,
                    reason=f"status changed to {order.status.value}",
                )
            if order.order_type != OrderType.market:
                return SkippedOutcome(
                    kind="skipped", order_id=order_id, reason="non-market order"
                )
            quote_cents = await self._quote_service.get_quote(order.ticker)
            if quote_cents is None:
                return SkippedOutcome(
                    kind="skipped", order_id=order_id, reason="no quote available"
                )
            portfolio = await self._lock_portfolio(session, order.portfolio_id)
            if portfolio is None:
                return SkippedOutcome(
                    kind="skipped", order_id=order_id, reason="portfolio missing"
                )
            notional_cents = quote_cents * order.quantity
            if order.side == OrderSide.buy:
                outcome = await self._apply_buy(
                    session=session,
                    order=order,
                    portfolio=portfolio,
                    quote_cents=quote_cents,
                    notional_cents=notional_cents,
                )
            else:
                outcome = await self._apply_sell(
                    session=session,
                    order=order,
                    portfolio=portfolio,
                    quote_cents=quote_cents,
                    notional_cents=notional_cents,
                )
            await session.commit()
            return outcome

    async def _lock_order(
        self, session: AsyncSession, order_id: uuid.UUID
    ) -> PaperOrder | None:
        stmt = select(PaperOrder).where(PaperOrder.id == order_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _lock_portfolio(
        self, session: AsyncSession, portfolio_id: uuid.UUID
    ) -> PaperPortfolio | None:
        stmt = (
            select(PaperPortfolio)
            .where(PaperPortfolio.id == portfolio_id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _lock_open_position(
        self, session: AsyncSession, portfolio_id: uuid.UUID, ticker: str
    ) -> PaperPosition | None:
        stmt = (
            select(PaperPosition)
            .where(PaperPosition.portfolio_id == portfolio_id)
            .where(PaperPosition.ticker == ticker)
            .where(PaperPosition.closed_at.is_(None))
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _apply_buy(
        self,
        *,
        session: AsyncSession,
        order: PaperOrder,
        portfolio: PaperPortfolio,
        quote_cents: int,
        notional_cents: int,
    ) -> FillOutcome:
        if portfolio.cash_cents < notional_cents:
            order.status = OrderStatus.rejected
            return RejectedOutcome(
                kind="rejected", order_id=order.id, reason="insufficient cash"
            )
        portfolio.cash_cents -= notional_cents
        existing = await self._lock_open_position(session, portfolio.id, order.ticker)
        if existing is None:
            session.add(
                PaperPosition(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio.id,
                    ticker=order.ticker,
                    quantity=order.quantity,
                    avg_cost_cents=quote_cents,
                    opened_at=_utcnow(),
                )
            )
        else:
            combined_quantity = existing.quantity + order.quantity
            blended_cost = (
                existing.avg_cost_cents * existing.quantity + quote_cents * order.quantity
            ) // combined_quantity
            existing.quantity = combined_quantity
            existing.avg_cost_cents = blended_cost
        _mark_filled(order, quote_cents)
        return FilledOutcome(
            kind="filled", order_id=order.id, fill_price_cents=quote_cents
        )

    async def _apply_sell(
        self,
        *,
        session: AsyncSession,
        order: PaperOrder,
        portfolio: PaperPortfolio,
        quote_cents: int,
        notional_cents: int,
    ) -> FillOutcome:
        position = await self._lock_open_position(session, portfolio.id, order.ticker)
        if position is None:
            order.status = OrderStatus.rejected
            return RejectedOutcome(
                kind="rejected", order_id=order.id, reason="no open position"
            )
        if position.quantity < order.quantity:
            order.status = OrderStatus.rejected
            return RejectedOutcome(
                kind="rejected", order_id=order.id, reason="insufficient shares"
            )
        position.quantity -= order.quantity
        portfolio.cash_cents += notional_cents
        if position.quantity == 0:
            position.closed_at = _utcnow()
        _mark_filled(order, quote_cents)
        return FilledOutcome(
            kind="filled", order_id=order.id, fill_price_cents=quote_cents
        )


def _mark_filled(order: PaperOrder, fill_price_cents: int) -> None:
    order.status = OrderStatus.filled
    order.filled_price_cents = fill_price_cents
    order.filled_at = _utcnow()


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "FillOutcome",
    "FillResult",
    "FilledOutcome",
    "PaperFiller",
    "RejectedOutcome",
    "SkippedOutcome",
]
