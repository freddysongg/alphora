from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.services.universe_resolver import (
    EmptyUniverseError,
    WatchlistNotFoundError,
    resolve_watchlist_tickers,
)


@pytest.mark.asyncio
async def test_resolve_returns_tickers_in_added_at_order(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="manual")
    db_session.add(watchlist)
    db_session.add(
        WatchlistMember(id=uuid.uuid4(), watchlist_id=watchlist.id, ticker="SPY")
    )
    db_session.add(
        WatchlistMember(id=uuid.uuid4(), watchlist_id=watchlist.id, ticker="QQQ")
    )
    await db_session.commit()

    tickers = await resolve_watchlist_tickers(db_session, watchlist.id)
    assert tickers == ["SPY", "QQQ"]


@pytest.mark.asyncio
async def test_resolve_empty_watchlist_raises_empty(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="empty research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    with pytest.raises(EmptyUniverseError) as excinfo:
        await resolve_watchlist_tickers(db_session, watchlist.id)
    assert str(watchlist.id) in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_missing_watchlist_raises_not_found(
    db_session: AsyncSession,
) -> None:
    missing = uuid.uuid4()
    with pytest.raises(WatchlistNotFoundError) as excinfo:
        await resolve_watchlist_tickers(db_session, missing)
    assert str(missing) in str(excinfo.value)
