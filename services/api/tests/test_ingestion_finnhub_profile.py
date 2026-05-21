import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EvidenceChunk
from app.services.ingestion.finnhub_profile import ingest_finnhub_profile
from app.services.source_clients.finnhub import FinnhubCompanyProfile


def _profile() -> FinnhubCompanyProfile:
    return FinnhubCompanyProfile(
        country="US",
        currency="USD",
        exchange="NASDAQ NMS - GLOBAL MARKET",
        finnhub_industry="Technology",
        ipo=date(1980, 12, 12),
        logo="https://example.com/aapl.png",
        market_capitalization=3000000.0,
        name="Apple Inc",
        phone="14089961010",
        share_outstanding=15600.0,
        ticker="AAPL",
        weburl="https://www.apple.com/",
    )


def _hash(profile: FinnhubCompanyProfile) -> str:
    body = json.dumps(profile.model_dump(mode="json"), default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@pytest.mark.asyncio
async def test_ingest_finnhub_profile_writes_single_chunk(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    result = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    assert result.source == "finnhub_profile"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    attrs = chunks[0].attributes
    assert attrs["country"] == "US"
    assert attrs["finnhub_industry"] == "Technology"
    assert attrs["market_capitalization"] == 3000000.0
    assert "Technology" in chunks[0].text


@pytest.mark.asyncio
async def test_ingest_finnhub_profile_is_idempotent(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    a = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    b = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_backfill_populates_entity_attributes_when_entity_exists(
    db_session: AsyncSession,
) -> None:
    async with db_session.begin():
        entity = Entity(
            type="company",
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={},
            attributes={},
            ticker_normalized="AAPL",
            confidence=1.0,
            needs_review=False,
        )
        db_session.add(entity)

    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )

    refreshed = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalar_one()
    assert refreshed.attributes["country"] == "US"
    assert refreshed.attributes["currency"] == "USD"
    assert refreshed.attributes["exchange"] == "NASDAQ NMS - GLOBAL MARKET"
    assert refreshed.attributes["finnhub_industry"] == "Technology"
    assert refreshed.attributes["ipo_date"] == "1980-12-12"
    assert refreshed.attributes["weburl"] == "https://www.apple.com/"
    assert "market_capitalization" not in refreshed.attributes
    assert "share_outstanding" not in refreshed.attributes


@pytest.mark.asyncio
async def test_backfill_does_not_create_entity_when_missing(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    entities = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalars().all()
    assert entities == []


@pytest.mark.asyncio
async def test_backfill_overwrites_changed_fields_and_keeps_same(
    db_session: AsyncSession,
) -> None:
    async with db_session.begin():
        entity = Entity(
            type="company",
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={},
            attributes={
                "country": "US",
                "finnhub_industry": "Consumer Electronics",
                "unrelated_existing_key": "preserved",
            },
            ticker_normalized="AAPL",
            confidence=1.0,
            needs_review=False,
        )
        db_session.add(entity)

    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )

    refreshed = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalar_one()
    assert refreshed.attributes["country"] == "US"
    assert refreshed.attributes["finnhub_industry"] == "Technology"
    assert refreshed.attributes["unrelated_existing_key"] == "preserved"
