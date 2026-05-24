import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import asc, select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.db.models_market import Watchlist, WatchlistMember
from app.schemas.market import (
    ResearchRebuildRequest,
    ResearchRebuildResponse,
    WatchlistCreate,
    WatchlistDetail,
    WatchlistMemberAdd,
    WatchlistMemberPublic,
    WatchlistPublic,
)
from app.services.research_watchlist_builder import (
    ResearchBuilderError,
    build_research_watchlist,
)
from app.services.universe_resolver import WatchlistNotFoundError

router = APIRouter()


@router.get("", response_model=list[WatchlistPublic])
async def list_watchlists(session: SessionDep) -> list[WatchlistPublic]:
    stmt = select(Watchlist).order_by(asc(Watchlist.created_at))
    rows = (await session.execute(stmt)).scalars().all()
    return [WatchlistPublic.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=WatchlistPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_watchlist(
    payload: WatchlistCreate, session: SessionDep
) -> WatchlistPublic:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name=payload.name,
        source=payload.source,
        is_active=payload.is_active,
    )
    session.add(watchlist)
    await session.commit()
    await session.refresh(watchlist)
    return WatchlistPublic.model_validate(watchlist)


@router.get("/{watchlist_id}", response_model=WatchlistDetail)
async def get_watchlist(
    watchlist_id: uuid.UUID, session: SessionDep
) -> WatchlistDetail:
    stmt = (
        select(Watchlist)
        .where(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.members))
    )
    watchlist = (await session.execute(stmt)).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="watchlist not found"
        )
    return WatchlistDetail.model_validate(
        {
            "id": watchlist.id,
            "name": watchlist.name,
            "source": watchlist.source,
            "is_active": watchlist.is_active,
            "last_built_at": watchlist.last_built_at,
            "created_at": watchlist.created_at,
            "members": [
                WatchlistMemberPublic.model_validate(member)
                for member in watchlist.members
            ],
        }
    )


@router.post(
    "/{watchlist_id}/members",
    response_model=WatchlistMemberPublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_watchlist_member(
    watchlist_id: uuid.UUID,
    payload: WatchlistMemberAdd,
    session: SessionDep,
) -> WatchlistMemberPublic:
    watchlist = (
        await session.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    ).scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="watchlist not found"
        )
    existing = (
        await session.execute(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .where(WatchlistMember.ticker == payload.ticker)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ticker already in watchlist",
        )
    member = WatchlistMember(
        id=uuid.uuid4(),
        watchlist_id=watchlist_id,
        ticker=payload.ticker,
        notes=payload.notes,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return WatchlistMemberPublic.model_validate(member)


@router.delete(
    "/{watchlist_id}/members/{ticker}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_watchlist_member(
    watchlist_id: uuid.UUID, ticker: str, session: SessionDep
) -> None:
    normalized = ticker.strip().upper()
    existing = (
        await session.execute(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .where(WatchlistMember.ticker == normalized)
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="watchlist member not found",
        )
    await session.delete(existing)
    await session.commit()


@router.post(
    "/{watchlist_id}/rebuild-research",
    response_model=ResearchRebuildResponse,
)
async def rebuild_research_watchlist(
    watchlist_id: uuid.UUID,
    payload: ResearchRebuildRequest,
    session: SessionDep,
) -> ResearchRebuildResponse:
    try:
        count = await build_research_watchlist(
            session,
            watchlist_id=watchlist_id,
            evidence_window_hours=payload.evidence_window_hours,
            min_belief=payload.min_belief,
            max_tickers=payload.max_tickers,
        )
    except WatchlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ResearchBuilderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ResearchRebuildResponse(watchlist_id=watchlist_id, count=count)


__all__ = ["router"]
