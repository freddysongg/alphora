"""Ingestion tests for Phase 7 sources: capitol_trades, polymarket_data,
finnhub_news, cme_fedwatch, fed_press, gdelt. Each adapter follows the
existing pattern (`insert_or_get_evidence` + `insert_chunks`); these tests
exercise the happy path plus content-hash idempotency."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence
from app.services.ingestion.cme_fedwatch import ingest_cme_fedwatch
from app.services.ingestion.fed_press import ingest_fed_press
from app.services.ingestion.finnhub_news import ingest_finnhub_news
from app.services.ingestion.gdelt import ingest_gdelt_articles
from app.services.ingestion.polymarket_price_history import (
    ingest_polymarket_price_history,
)
from app.services.source_clients.cme_fedwatch import (
    FedWatchMeeting,
    FedWatchProbability,
)
from app.services.source_clients.fed_press import FedPressItem
from app.services.source_clients.finnhub import FinnhubNewsItem
from app.services.source_clients.gdelt import GdeltArticle
from app.services.source_clients.polymarket_data import (
    PolymarketPriceHistory,
    PolymarketPricePoint,
)


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, default=str, sort_keys=True).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_ingest_polymarket_price_history_writes_chunks(
    db_session: AsyncSession,
) -> None:
    payload = PolymarketPriceHistory(
        market="m1",
        interval="1d",
        history=[
            PolymarketPricePoint(t=1714521600, p=0.42, v=100.0),
            PolymarketPricePoint(t=1714608000, p=0.43, v=200.0),
        ],
    )
    h = _hash_payload(payload.model_dump(mode="json"))

    result = await ingest_polymarket_price_history(
        session=db_session, payload=payload, content_hash=h, raw_url=None
    )

    assert result.source == "polymarket_data"
    assert result.chunk_count == 2
    evidence = (await db_session.execute(select(Evidence))).scalars().all()
    assert len(evidence) == 1
    assert evidence[0].source == "polymarket_data"


@pytest.mark.asyncio
async def test_ingest_polymarket_price_history_is_idempotent(
    db_session: AsyncSession,
) -> None:
    payload = PolymarketPriceHistory(
        market="m1",
        interval="1d",
        history=[PolymarketPricePoint(t=1, p=0.5)],
    )
    h = _hash_payload(payload.model_dump(mode="json"))
    a = await ingest_polymarket_price_history(
        session=db_session, payload=payload, content_hash=h, raw_url=None
    )
    b = await ingest_polymarket_price_history(
        session=db_session, payload=payload, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id


def _finnhub_news() -> list[FinnhubNewsItem]:
    return [
        FinnhubNewsItem(
            id=1,
            category="company",
            headline="h1",
            source="CNBC",
            url="https://example.com/a",
            published_at=datetime(2026, 5, 15, tzinfo=UTC),
            related="AAPL",
        ),
        FinnhubNewsItem(
            id=2,
            category="company",
            headline="h2",
            source="Reuters",
            url="https://example.com/b",
            published_at=datetime(2026, 5, 16, tzinfo=UTC),
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_finnhub_news_writes_chunks(db_session: AsyncSession) -> None:
    items = _finnhub_news()
    h = _hash_payload([i.model_dump(mode="json") for i in items])

    result = await ingest_finnhub_news(
        session=db_session, items=items, content_hash=h, raw_url=None
    )

    assert result.source == "finnhub_news"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_finnhub_news_is_idempotent(db_session: AsyncSession) -> None:
    items = _finnhub_news()
    h = _hash_payload([i.model_dump(mode="json") for i in items])
    a = await ingest_finnhub_news(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_news(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id


def _fedwatch_meeting() -> FedWatchMeeting:
    return FedWatchMeeting(
        as_of=datetime(2026, 5, 19, 18, tzinfo=UTC),
        meeting_date=date(2026, 6, 17),
        current_target_low_bps=425,
        current_target_high_bps=450,
        probabilities=[
            FedWatchProbability(target_low_bps=400, target_high_bps=425, probability=0.35),
            FedWatchProbability(target_low_bps=425, target_high_bps=450, probability=0.6),
            FedWatchProbability(target_low_bps=450, target_high_bps=475, probability=0.05),
        ],
    )


@pytest.mark.asyncio
async def test_ingest_cme_fedwatch_writes_chunks(db_session: AsyncSession) -> None:
    meeting = _fedwatch_meeting()
    h = _hash_payload(meeting.model_dump(mode="json"))
    result = await ingest_cme_fedwatch(
        session=db_session, meeting=meeting, content_hash=h, raw_url=None
    )
    assert result.source == "cme_fedwatch"
    assert result.chunk_count == 3


@pytest.mark.asyncio
async def test_ingest_cme_fedwatch_is_idempotent(db_session: AsyncSession) -> None:
    meeting = _fedwatch_meeting()
    h = _hash_payload(meeting.model_dump(mode="json"))
    a = await ingest_cme_fedwatch(
        session=db_session, meeting=meeting, content_hash=h, raw_url=None
    )
    b = await ingest_cme_fedwatch(
        session=db_session, meeting=meeting, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id


def _fed_press_items() -> list[FedPressItem]:
    return [
        FedPressItem(
            id="monetary20260507a",
            kind="monetary",
            title="FOMC statement",
            url="https://www.federalreserve.gov/m",
            published_at=datetime(2026, 5, 7, 18, tzinfo=UTC),
        ),
        FedPressItem(
            id="powell20260512a",
            kind="speech",
            title="Outlook",
            url="https://www.federalreserve.gov/s",
            published_at=datetime(2026, 5, 12, 13, tzinfo=UTC),
            speaker="Jerome H. Powell",
            venue="CFR",
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_fed_press_writes_chunks(db_session: AsyncSession) -> None:
    items = _fed_press_items()
    h = _hash_payload([i.model_dump(mode="json") for i in items])
    result = await ingest_fed_press(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert result.source == "fed_press"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_fed_press_is_idempotent(db_session: AsyncSession) -> None:
    items = _fed_press_items()
    h = _hash_payload([i.model_dump(mode="json") for i in items])
    a = await ingest_fed_press(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    b = await ingest_fed_press(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id


def _gdelt_articles() -> list[GdeltArticle]:
    return [
        GdeltArticle(
            url="https://example.com/a",
            title="t1",
            seendate=datetime(2026, 5, 1, tzinfo=UTC),
            domain="reuters.com",
            language="English",
            sourcecountry="US",
            tone=-1.5,
            themes=["TRADE", "GEOPOLITICS"],
        ),
        GdeltArticle(
            url="https://example.com/b",
            title="t2",
            seendate=datetime(2026, 5, 2, tzinfo=UTC),
            tone=2.0,
            themes=[],
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_gdelt_articles_writes_chunks(db_session: AsyncSession) -> None:
    articles = _gdelt_articles()
    h = _hash_payload([a.model_dump(mode="json") for a in articles])
    result = await ingest_gdelt_articles(
        session=db_session, articles=articles, content_hash=h, raw_url=None
    )
    assert result.source == "gdelt"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_gdelt_articles_is_idempotent(db_session: AsyncSession) -> None:
    articles = _gdelt_articles()
    h = _hash_payload([a.model_dump(mode="json") for a in articles])
    a = await ingest_gdelt_articles(
        session=db_session, articles=articles, content_hash=h, raw_url=None
    )
    b = await ingest_gdelt_articles(
        session=db_session, articles=articles, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
