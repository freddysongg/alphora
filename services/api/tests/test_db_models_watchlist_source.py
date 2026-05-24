from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource


def test_watchlist_source_enum_values() -> None:
    assert WatchlistSource.manual.value == "manual"
    assert WatchlistSource.research.value == "research"
    assert {m.value for m in WatchlistSource} == {"manual", "research"}


@pytest.mark.asyncio
async def test_watchlist_persists_source_is_active_last_built_at(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="test research",
        source=WatchlistSource.research.value,
        is_active=False,
    )
    db_session.add(watchlist)
    await db_session.commit()

    fetched = await db_session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist.id)
    )
    assert fetched is not None
    assert fetched.source == "research"
    assert fetched.is_active is False
    assert fetched.last_built_at is None


@pytest.mark.asyncio
async def test_watchlist_source_defaults_to_manual_when_omitted(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(id=uuid.uuid4(), name="default")
    db_session.add(watchlist)
    await db_session.commit()
    fetched = await db_session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist.id)
    )
    assert fetched is not None
    assert fetched.source == "manual"
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_watchlist_member_persists_hypothesis_id_and_metadata(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    hypo_id = uuid.uuid4()
    member = WatchlistMember(
        id=uuid.uuid4(),
        watchlist_id=watchlist.id,
        ticker="NVDA",
        hypothesis_id=hypo_id,
        member_metadata={"belief": 0.78, "last_activity_iso": "2026-05-22T14:00:00Z"},
    )
    db_session.add(member)
    await db_session.commit()
    fetched = await db_session.scalar(
        select(WatchlistMember).where(WatchlistMember.id == member.id)
    )
    assert fetched is not None
    assert fetched.hypothesis_id == hypo_id
    assert fetched.member_metadata == {
        "belief": 0.78,
        "last_activity_iso": "2026-05-22T14:00:00Z",
    }
