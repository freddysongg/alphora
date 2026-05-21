import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_price_target import ingest_finnhub_price_target
from app.services.source_clients.finnhub import FinnhubPriceTarget


def _target() -> FinnhubPriceTarget:
    return FinnhubPriceTarget(
        symbol="AAPL",
        last_updated=datetime(2026, 5, 18, 14, 30, tzinfo=UTC),
        target_high=250.0,
        target_low=175.0,
        target_mean=215.0,
        target_median=210.0,
        number_of_analysts=38,
    )


@pytest.mark.asyncio
async def test_ingest_finnhub_price_target_writes_single_chunk(
    db_session: AsyncSession,
) -> None:
    target = _target()
    body = json.dumps(target.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_price_target(
        session=db_session,
        symbol="AAPL",
        target=target,
        content_hash=h,
        raw_url=None,
    )
    assert result.source == "finnhub_price_target"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert "median=210" in chunks[0].text
    assert chunks[0].attributes["target_median"] == 210.0
    assert chunks[0].attributes["number_of_analysts"] == 38


@pytest.mark.asyncio
async def test_ingest_finnhub_price_target_is_idempotent(
    db_session: AsyncSession,
) -> None:
    target = _target()
    body = json.dumps(target.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_price_target(
        session=db_session, symbol="AAPL", target=target, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_price_target(
        session=db_session, symbol="AAPL", target=target, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
