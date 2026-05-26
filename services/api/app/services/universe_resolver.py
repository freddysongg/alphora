"""Universe resolution -- turn a watchlist_id into a list of tickers.

Pure read function used by:
- the spawn helper (`strategy_runner_spawn.py`)
- the CLI `show` command (`app/cli/watchlists.py`)
- future Phase 8 commands that need a tradable universe

The runner does NOT call this directly -- it's per-ticker and receives
its ticker as a constructor argument from the spawn helper.
"""
from __future__ import annotations

import uuid

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_market import Watchlist, WatchlistMember


class WatchlistNotFoundError(LookupError):
    """Raised when the requested watchlist_id has no row in `watchlists`."""


class EmptyUniverseError(ValueError):
    """Raised when a watchlist exists but has zero members.

    The strategy runner refuses to start against an empty universe -- a
    research-driven watchlist that hasn't been built yet, or a manual
    watchlist whose tickers were all removed, would otherwise produce
    silently-no-op runners.
    """


async def resolve_watchlist_tickers(
    session: AsyncSession, watchlist_id: uuid.UUID
) -> list[str]:
    """Return the list of tickers for `watchlist_id` in added_at order.

    Raises WatchlistNotFoundError if no watchlist row exists.
    Raises EmptyUniverseError if the watchlist has zero members.
    """
    watchlist = await session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist_id)
    )
    if watchlist is None:
        raise WatchlistNotFoundError(f"watchlist {watchlist_id} not found")
    rows = (
        await session.execute(
            select(WatchlistMember.ticker)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .order_by(asc(WatchlistMember.added_at))
        )
    ).scalars().all()
    if not rows:
        raise EmptyUniverseError(
            f"watchlist {watchlist_id} has zero members; "
            "runner refuses to spawn against an empty universe"
        )
    return list(rows)


__all__ = [
    "EmptyUniverseError",
    "WatchlistNotFoundError",
    "resolve_watchlist_tickers",
]
