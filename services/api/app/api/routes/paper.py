import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.db.models_paper import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    PaperPortfolio,
    PaperPosition,
)
from app.schemas.common import OrderStatusEnum
from app.schemas.paper import (
    CreatePaperOrderRequest,
    PaperOrderPublic,
    PaperPortfolioSnapshot,
    PaperPositionPublic,
)

router = APIRouter()

_DEFAULT_PORTFOLIO_NAME: str = "Default"
_DEFAULT_PORTFOLIO_CASH_CENTS: int = 100_000 * 100


async def _get_or_create_default_portfolio(session: SessionDep) -> PaperPortfolio:
    existing_stmt = (
        select(PaperPortfolio).order_by(asc(PaperPortfolio.created_at)).limit(1)
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    portfolio = PaperPortfolio(
        id=uuid.uuid4(),
        name=_DEFAULT_PORTFOLIO_NAME,
        cash_cents=_DEFAULT_PORTFOLIO_CASH_CENTS,
    )
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    return portfolio


async def _load_open_position(
    session: SessionDep, portfolio_id: uuid.UUID, ticker: str
) -> PaperPosition | None:
    stmt = (
        select(PaperPosition)
        .where(PaperPosition.portfolio_id == portfolio_id)
        .where(PaperPosition.ticker == ticker)
        .where(PaperPosition.closed_at.is_(None))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@router.post(
    "/orders",
    response_model=PaperOrderPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_paper_order(
    payload: CreatePaperOrderRequest, session: SessionDep
) -> PaperOrderPublic:
    portfolio = (
        await session.execute(
            select(PaperPortfolio).where(PaperPortfolio.id == payload.portfolio_id)
        )
    ).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found"
        )
    if payload.side.value == OrderSide.sell.value:
        open_position = await _load_open_position(
            session, payload.portfolio_id, payload.ticker
        )
        if open_position is None or open_position.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot sell without an open long position",
            )
    order = PaperOrder(
        id=uuid.uuid4(),
        portfolio_id=payload.portfolio_id,
        ticker=payload.ticker,
        side=OrderSide(payload.side.value),
        quantity=payload.quantity,
        order_type=OrderType(payload.order_type.value),
        status=OrderStatus.pending,
        source_run_id=payload.source_run_id,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return PaperOrderPublic.model_validate(order)


@router.get("/orders", response_model=list[PaperOrderPublic])
async def list_paper_orders(
    session: SessionDep,
    portfolio_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[OrderStatusEnum | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PaperOrderPublic]:
    stmt = (
        select(PaperOrder)
        .where(PaperOrder.portfolio_id == portfolio_id)
        .order_by(desc(PaperOrder.submitted_at))
    )
    if status_filter is not None:
        stmt = stmt.where(PaperOrder.status == OrderStatus(status_filter.value))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [PaperOrderPublic.model_validate(row) for row in rows]


def _build_position_public(position: PaperPosition) -> PaperPositionPublic:
    return PaperPositionPublic.model_validate(
        {
            "id": position.id,
            "portfolio_id": position.portfolio_id,
            "ticker": position.ticker,
            "quantity": position.quantity,
            "avg_cost_cents": position.avg_cost_cents,
            "mark_cents": position.avg_cost_cents,
            "opened_at": position.opened_at,
            "closed_at": position.closed_at,
        }
    )


@router.get("/portfolio", response_model=PaperPortfolioSnapshot)
async def get_paper_portfolio(
    session: SessionDep,
    portfolio_id: Annotated[uuid.UUID | None, Query()] = None,
) -> PaperPortfolioSnapshot:
    if portfolio_id is None:
        portfolio = await _get_or_create_default_portfolio(session)
    else:
        stmt = (
            select(PaperPortfolio)
            .where(PaperPortfolio.id == portfolio_id)
            .options(selectinload(PaperPortfolio.positions))
        )
        portfolio_loaded = (await session.execute(stmt)).scalar_one_or_none()
        if portfolio_loaded is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found"
            )
        portfolio = portfolio_loaded
    positions_stmt = (
        select(PaperPosition)
        .where(PaperPosition.portfolio_id == portfolio.id)
        .where(PaperPosition.closed_at.is_(None))
    )
    open_positions = list((await session.execute(positions_stmt)).scalars().all())
    public_positions = [_build_position_public(position) for position in open_positions]
    equity_cents = sum(p.mark_cents * p.quantity for p in public_positions)
    cost_cents = sum(p.avg_cost_cents * p.quantity for p in public_positions)
    unrealized_pl_cents = equity_cents - cost_cents
    return PaperPortfolioSnapshot(
        id=portfolio.id,
        name=portfolio.name,
        cash_cents=portfolio.cash_cents,
        equity_cents=equity_cents,
        unrealized_pl_cents=unrealized_pl_cents,
        realized_pl_cents=0,
        positions=public_positions,
    )


__all__ = ["router"]
