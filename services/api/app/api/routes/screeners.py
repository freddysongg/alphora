import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.db.models_market import (
    ScreenerResult,
    ScreenerRun,
    Watchlist,
)
from app.schemas.common import ScreenerUniverseEnum
from app.schemas.market import (
    ScreenerResultPublic,
    ScreenerRunPublic,
    ScreenerRunRequest,
    ScreenerRunResponse,
)
from app.services.screener_stub import get_universe_tickers, score_tickers

router = APIRouter()


async def _resolve_universe_tickers(
    session: SessionDep, request: ScreenerRunRequest
) -> list[str]:
    if request.universe == ScreenerUniverseEnum.watchlist:
        if request.watchlist_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="watchlist_id is required for watchlist universe",
            )
        stmt = (
            select(Watchlist)
            .where(Watchlist.id == request.watchlist_id)
            .options(selectinload(Watchlist.members))
        )
        watchlist = (await session.execute(stmt)).scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="watchlist not found"
            )
        return [member.ticker for member in watchlist.members]
    return get_universe_tickers(request.universe)


@router.post(
    "/run",
    response_model=ScreenerRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_screener(
    payload: ScreenerRunRequest, session: SessionDep
) -> ScreenerRunResponse:
    tickers = await _resolve_universe_tickers(session, payload)
    scored = score_tickers(tickers, payload.factor_weights)
    capped = scored[: payload.limit]
    screener_run = ScreenerRun(
        id=uuid.uuid4(),
        universe=payload.universe.value,
        factor_weights=dict(payload.factor_weights),
        finished_at=datetime.now(UTC),
        result_count=len(capped),
    )
    session.add(screener_run)
    result_rows: list[ScreenerResult] = []
    for ticker, total_score, factor_scores in capped:
        row = ScreenerResult(
            id=uuid.uuid4(),
            screener_run_id=screener_run.id,
            ticker=ticker,
            score=total_score,
            factor_scores=factor_scores,
        )
        session.add(row)
        result_rows.append(row)
    await session.commit()
    return ScreenerRunResponse(
        screener_run=ScreenerRunPublic.model_validate(screener_run),
        results=[ScreenerResultPublic.model_validate(row) for row in result_rows],
    )


@router.get("/runs/{screener_run_id}", response_model=ScreenerRunResponse)
async def get_screener_run(
    screener_run_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScreenerRunResponse:
    run_stmt = select(ScreenerRun).where(ScreenerRun.id == screener_run_id)
    run = (await session.execute(run_stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="screener run not found"
        )
    result_stmt = (
        select(ScreenerResult)
        .where(ScreenerResult.screener_run_id == screener_run_id)
        .order_by(desc(ScreenerResult.score), asc(ScreenerResult.ticker))
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(result_stmt)).scalars().all()
    return ScreenerRunResponse(
        screener_run=ScreenerRunPublic.model_validate(run),
        results=[ScreenerResultPublic.model_validate(row) for row in rows],
    )


__all__ = ["router"]
