from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.services.research_watchlist_builder import (
    ResearchBuilderError,
    build_research_watchlist,
)


def _make_entity(ticker: str) -> Entity:
    return Entity(
        id=uuid.uuid4(),
        type=EntityType.company.value,
        canonical_name=ticker,
        ticker_normalized=ticker,
    )


def _make_hypothesis(
    *,
    entity_ids: list[uuid.UUID],
    belief: float,
    last_activity_at: datetime,
    status: HypothesisStatus = HypothesisStatus.active,
) -> Hypothesis:
    return Hypothesis(
        id=uuid.uuid4(),
        claim_text="test claim",
        scope_entity_ids=[str(eid) for eid in entity_ids],
        status=status.value,
        belief=belief,
        last_activity_at=last_activity_at,
    )


@pytest.mark.asyncio
async def test_builder_populates_research_watchlist_with_matching_tickers(
    db_session: AsyncSession,
) -> None:
    nvda = _make_entity("NVDA")
    aapl = _make_entity("AAPL")
    db_session.add_all([nvda, aapl])
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[nvda.id],
            belief=0.8,
            last_activity_at=now - timedelta(hours=2),
        )
    )
    db_session.add(
        _make_hypothesis(
            entity_ids=[aapl.id],
            belief=0.65,
            last_activity_at=now - timedelta(hours=6),
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="active research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 2

    members = (
        await db_session.execute(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist.id
            )
        )
    ).scalars().all()
    tickers = sorted(m.ticker for m in members)
    assert tickers == ["AAPL", "NVDA"]
    for member in members:
        assert member.hypothesis_id is not None
        assert isinstance(member.member_metadata, dict)
        assert "belief" in member.member_metadata
        assert "last_activity_iso" in member.member_metadata

    refreshed = await db_session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist.id)
    )
    assert refreshed is not None
    assert refreshed.last_built_at is not None


@pytest.mark.asyncio
async def test_builder_excludes_below_belief_threshold(
    db_session: AsyncSession,
) -> None:
    spy = _make_entity("SPY")
    db_session.add(spy)
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[spy.id],
            belief=0.4,
            last_activity_at=now - timedelta(hours=1),
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_builder_excludes_stale_activity(db_session: AsyncSession) -> None:
    qqq = _make_entity("QQQ")
    db_session.add(qqq)
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[qqq.id],
            belief=0.9,
            last_activity_at=now - timedelta(hours=48),
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_builder_excludes_non_active_status(
    db_session: AsyncSession,
) -> None:
    iwm = _make_entity("IWM")
    db_session.add(iwm)
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[iwm.id],
            belief=0.9,
            last_activity_at=now - timedelta(hours=1),
            status=HypothesisStatus.proposed,
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_builder_deduplicates_when_multiple_hypotheses_share_ticker(
    db_session: AsyncSession,
) -> None:
    msft = _make_entity("MSFT")
    db_session.add(msft)
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[msft.id],
            belief=0.7,
            last_activity_at=now - timedelta(hours=1),
        )
    )
    db_session.add(
        _make_hypothesis(
            entity_ids=[msft.id],
            belief=0.85,
            last_activity_at=now - timedelta(minutes=30),
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 1
    members = (
        await db_session.execute(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist.id
            )
        )
    ).scalars().all()
    assert [m.ticker for m in members] == ["MSFT"]
    assert members[0].member_metadata is not None
    assert members[0].member_metadata["belief"] == 0.85


@pytest.mark.asyncio
async def test_builder_skips_entities_without_ticker_normalized(
    db_session: AsyncSession,
) -> None:
    theme_entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.theme.value,
        canonical_name="AI infrastructure",
        ticker_normalized=None,
    )
    db_session.add(theme_entity)
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[theme_entity.id],
            belief=0.95,
            last_activity_at=now - timedelta(hours=1),
        )
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_builder_replaces_existing_members(db_session: AsyncSession) -> None:
    nvda = _make_entity("NVDA")
    db_session.add(nvda)
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    db_session.add(
        WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id,
            ticker="STALE",
            notes="should be wiped",
        )
    )
    now = datetime.now(UTC)
    db_session.add(
        _make_hypothesis(
            entity_ids=[nvda.id],
            belief=0.9,
            last_activity_at=now - timedelta(hours=1),
        )
    )
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=25,
    )
    assert count == 1
    members = (
        await db_session.execute(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist.id
            )
        )
    ).scalars().all()
    assert [m.ticker for m in members] == ["NVDA"]


@pytest.mark.asyncio
async def test_builder_rejects_manual_watchlist(db_session: AsyncSession) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="manual",
        source=WatchlistSource.manual.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    with pytest.raises(ResearchBuilderError) as excinfo:
        await build_research_watchlist(
            db_session,
            watchlist_id=watchlist.id,
            evidence_window_hours=24,
            min_belief=0.6,
            max_tickers=25,
        )
    assert "manual" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_builder_respects_max_tickers_by_belief_desc(
    db_session: AsyncSession,
) -> None:
    entities = [_make_entity(t) for t in ("A", "B", "C", "D", "E")]
    beliefs = [0.7, 0.95, 0.65, 0.8, 0.9]
    db_session.add_all(entities)
    now = datetime.now(UTC)
    for entity, belief in zip(entities, beliefs, strict=True):
        db_session.add(
            _make_hypothesis(
                entity_ids=[entity.id],
                belief=belief,
                last_activity_at=now - timedelta(hours=1),
            )
        )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    db_session.add(watchlist)
    await db_session.commit()

    count = await build_research_watchlist(
        db_session,
        watchlist_id=watchlist.id,
        evidence_window_hours=24,
        min_belief=0.6,
        max_tickers=3,
    )
    assert count == 3
    members = (
        await db_session.execute(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist.id
            )
        )
    ).scalars().all()
    tickers = sorted(m.ticker for m in members)
    assert tickers == ["B", "D", "E"]
