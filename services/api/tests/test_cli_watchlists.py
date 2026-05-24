from __future__ import annotations

import asyncio
import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli_app
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource

runner = CliRunner()


def test_cli_list_empty(initialized_schema: None) -> None:
    _ = initialized_schema
    result = runner.invoke(cli_app, ["watchlists", "list"])
    assert result.exit_code == 0, result.output
    assert "no watchlists" in result.output.lower()


def test_cli_create_manual_watchlist(initialized_schema: None) -> None:
    _ = initialized_schema
    result = runner.invoke(
        cli_app, ["watchlists", "create", "--name", "manual-test"]
    )
    assert result.exit_code == 0, result.output
    assert "manual-test" in result.output
    assert "source=manual" in result.output


def test_cli_create_research_watchlist(initialized_schema: None) -> None:
    _ = initialized_schema
    result = runner.invoke(
        cli_app,
        ["watchlists", "create", "--name", "research-test", "--source", "research"],
    )
    assert result.exit_code == 0, result.output
    assert "source=research" in result.output


def test_cli_add_and_remove_member_round_trip(initialized_schema: None) -> None:
    _ = initialized_schema
    created = runner.invoke(
        cli_app, ["watchlists", "create", "--name", "rr"]
    )
    assert created.exit_code == 0, created.output
    watchlist_id = _extract_id(created.output)
    add = runner.invoke(
        cli_app, ["watchlists", "add", watchlist_id, "--ticker", "spy"]
    )
    assert add.exit_code == 0, add.output
    assert "SPY" in add.output
    show = runner.invoke(cli_app, ["watchlists", "show", watchlist_id])
    assert show.exit_code == 0, show.output
    assert "SPY" in show.output
    remove = runner.invoke(
        cli_app, ["watchlists", "remove", watchlist_id, "--ticker", "SPY"]
    )
    assert remove.exit_code == 0, remove.output


@pytest.mark.asyncio
async def test_cli_rebuild_research_invokes_builder(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
    from app.db.session import session_factory

    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            type=EntityType.company.value,
            canonical_name="QQQ",
            ticker_normalized="QQQ",
        )
        watchlist = Watchlist(
            id=uuid.uuid4(),
            name="cli-research",
            source=WatchlistSource.research.value,
        )
        hypothesis = Hypothesis(
            id=uuid.uuid4(),
            claim_text="qqq momentum",
            scope_entity_ids=[str(entity.id)],
            status=HypothesisStatus.active.value,
            belief=0.9,
            last_activity_at=datetime.now(UTC) - timedelta(hours=2),
        )
        session.add_all([entity, watchlist, hypothesis])
        await session.commit()
        wid = str(watchlist.id)

    result = await asyncio.to_thread(
        runner.invoke,
        cli_app,
        ["watchlists", "rebuild-research", wid],
    )
    assert result.exit_code == 0, result.output
    assert "1" in result.output

    async with session_factory() as session:
        members = (
            await session.execute(
                select(WatchlistMember).where(WatchlistMember.watchlist_id == watchlist.id)
            )
        ).scalars().all()
        assert [m.ticker for m in members] == ["QQQ"]


def _extract_id(output: str) -> str:
    for line in output.splitlines():
        for token in line.split():
            try:
                return str(uuid.UUID(token))
            except ValueError:
                continue
    raise AssertionError(f"no uuid in output: {output!r}")
