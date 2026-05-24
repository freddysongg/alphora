"""`alphora-trade watchlists` subcommands.

Thin Typer adapter -- every command opens an async session, calls the
service-layer function, prints the result. No business logic here.
"""
from __future__ import annotations

import asyncio
import uuid

import typer
from sqlalchemy import asc, select

from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.db.session import session_factory
from app.services.research_watchlist_builder import (
    ResearchBuilderError,
    build_research_watchlist,
)
from app.services.universe_resolver import (
    EmptyUniverseError,
    WatchlistNotFoundError,
    resolve_watchlist_tickers,
)

app = typer.Typer(help="Manage strategy-runner watchlists.")


@app.command("list")
def cmd_list() -> None:
    """List all watchlists, oldest first."""
    asyncio.run(_list())


async def _list() -> None:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Watchlist).order_by(asc(Watchlist.created_at))
            )
        ).scalars().all()
    if not rows:
        typer.echo("no watchlists.")
        return
    for row in rows:
        typer.echo(
            f"{row.id}  name={row.name!r}  source={row.source}  "
            f"is_active={row.is_active}  last_built_at={row.last_built_at}"
        )


@app.command("create")
def cmd_create(
    name: str = typer.Option(..., "--name", help="Display name."),
    source: str = typer.Option(
        WatchlistSource.manual.value,
        "--source",
        help="manual | research",
    ),
    is_active: bool = typer.Option(True, "--is-active/--no-active"),
) -> None:
    """Create an empty watchlist."""
    allowed_sources = {s.value for s in WatchlistSource}
    if source not in allowed_sources:
        allowed_display = " | ".join(sorted(allowed_sources))
        raise typer.BadParameter(
            f"--source must be one of: {allowed_display}; got {source!r}"
        )
    asyncio.run(_create(name=name, source=source, is_active=is_active))


async def _create(*, name: str, source: str, is_active: bool) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name=name,
        source=source,
        is_active=is_active,
    )
    async with session_factory() as session:
        session.add(watchlist)
        await session.commit()
    typer.echo(
        f"{watchlist.id}  name={watchlist.name!r}  source={source}  "
        f"is_active={is_active}"
    )


@app.command("show")
def cmd_show(watchlist_id: str = typer.Argument(...)) -> None:
    """Show watchlist metadata + members."""
    asyncio.run(_show(_parse_uuid(watchlist_id)))


async def _show(watchlist_id: uuid.UUID) -> None:
    async with session_factory() as session:
        watchlist = await session.scalar(
            select(Watchlist).where(Watchlist.id == watchlist_id)
        )
        if watchlist is None:
            typer.echo(f"watchlist {watchlist_id} not found", err=True)
            raise typer.Exit(code=1)
        members = (
            await session.execute(
                select(WatchlistMember)
                .where(WatchlistMember.watchlist_id == watchlist_id)
                .order_by(asc(WatchlistMember.added_at))
            )
        ).scalars().all()
    typer.echo(
        f"{watchlist.id}  name={watchlist.name!r}  source={watchlist.source}  "
        f"is_active={watchlist.is_active}  last_built_at={watchlist.last_built_at}"
    )
    if not members:
        typer.echo("  (no members)")
        return
    for member in members:
        typer.echo(
            f"  {member.ticker}  hypothesis_id={member.hypothesis_id}  "
            f"metadata={member.member_metadata}"
        )


@app.command("add")
def cmd_add(
    watchlist_id: str = typer.Argument(...),
    ticker: str = typer.Option(..., "--ticker"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Add a ticker to a watchlist (manual entry)."""
    asyncio.run(
        _add(
            watchlist_id=_parse_uuid(watchlist_id),
            ticker=ticker.strip().upper(),
            notes=notes,
        )
    )


async def _add(
    *, watchlist_id: uuid.UUID, ticker: str, notes: str | None
) -> None:
    async with session_factory() as session:
        watchlist = await session.scalar(
            select(Watchlist).where(Watchlist.id == watchlist_id)
        )
        if watchlist is None:
            typer.echo(f"watchlist {watchlist_id} not found", err=True)
            raise typer.Exit(code=1)
        existing = await session.scalar(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .where(WatchlistMember.ticker == ticker)
        )
        if existing is not None:
            typer.echo(
                f"ticker {ticker} already in watchlist {watchlist_id}", err=True
            )
            raise typer.Exit(code=1)
        member = WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist_id,
            ticker=ticker,
            notes=notes,
        )
        session.add(member)
        await session.commit()
    typer.echo(f"added {ticker} to {watchlist_id}")


@app.command("remove")
def cmd_remove(
    watchlist_id: str = typer.Argument(...),
    ticker: str = typer.Option(..., "--ticker"),
) -> None:
    """Remove a ticker from a watchlist."""
    asyncio.run(
        _remove(
            watchlist_id=_parse_uuid(watchlist_id),
            ticker=ticker.strip().upper(),
        )
    )


async def _remove(*, watchlist_id: uuid.UUID, ticker: str) -> None:
    async with session_factory() as session:
        existing = await session.scalar(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .where(WatchlistMember.ticker == ticker)
        )
        if existing is None:
            typer.echo(
                f"ticker {ticker} not in watchlist {watchlist_id}", err=True
            )
            raise typer.Exit(code=1)
        await session.delete(existing)
        await session.commit()
    typer.echo(f"removed {ticker} from {watchlist_id}")


@app.command("rebuild-research")
def cmd_rebuild_research(
    watchlist_id: str = typer.Argument(...),
    evidence_window_hours: int = typer.Option(24, "--window-hours", min=1, max=168),
    min_belief: float = typer.Option(0.6, "--min-belief", min=0.0, max=1.0),
    max_tickers: int = typer.Option(25, "--max-tickers", min=1, max=100),
) -> None:
    """Replace the members of a research watchlist by re-querying the hypothesis graph."""
    asyncio.run(
        _rebuild(
            watchlist_id=_parse_uuid(watchlist_id),
            evidence_window_hours=evidence_window_hours,
            min_belief=min_belief,
            max_tickers=max_tickers,
        )
    )


async def _rebuild(
    *,
    watchlist_id: uuid.UUID,
    evidence_window_hours: int,
    min_belief: float,
    max_tickers: int,
) -> None:
    async with session_factory() as session:
        try:
            count = await build_research_watchlist(
                session,
                watchlist_id=watchlist_id,
                evidence_window_hours=evidence_window_hours,
                min_belief=min_belief,
                max_tickers=max_tickers,
            )
        except WatchlistNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ResearchBuilderError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"rebuilt research watchlist {watchlist_id} with {count} members")


@app.command("tickers")
def cmd_tickers(watchlist_id: str = typer.Argument(...)) -> None:
    """Print the resolved ticker list (what the runner spawn would see)."""
    asyncio.run(_tickers(_parse_uuid(watchlist_id)))


async def _tickers(watchlist_id: uuid.UUID) -> None:
    async with session_factory() as session:
        try:
            tickers = await resolve_watchlist_tickers(session, watchlist_id)
        except WatchlistNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except EmptyUniverseError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
    for ticker in tickers:
        typer.echo(ticker)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise typer.BadParameter(f"not a uuid: {value!r}") from exc


__all__ = ["app"]
