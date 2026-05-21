import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_recommendation import ingest_finnhub_recommendation
from app.services.source_clients.finnhub import FinnhubRecommendation


def _items() -> list[FinnhubRecommendation]:
    return [
        FinnhubRecommendation(
            symbol="AAPL",
            period=date(2026, 5, 1),
            buy=25,
            hold=8,
            sell=2,
            strong_buy=15,
            strong_sell=1,
        ),
        FinnhubRecommendation(
            symbol="AAPL",
            period=date(2026, 4, 1),
            buy=22,
            hold=9,
            sell=3,
            strong_buy=14,
            strong_sell=1,
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_finnhub_recommendation_writes_one_chunk_per_period(
    db_session: AsyncSession,
) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_recommendation(
        session=db_session,
        symbol="AAPL",
        items=items,
        content_hash=h,
        raw_url=None,
    )
    assert result.source == "finnhub_recommendation"
    assert result.chunk_count == 2

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    chunks_sorted = sorted(chunks, key=lambda c: c.chunk_index)
    assert "period=2026-05-01" in chunks_sorted[0].text
    assert chunks_sorted[0].attributes["buy"] == 25
    assert chunks_sorted[0].attributes["strong_buy"] == 15
    assert chunks_sorted[0].attributes["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_recommendation_is_idempotent(
    db_session: AsyncSession,
) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_recommendation(
        session=db_session, symbol="AAPL", items=items, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_recommendation(
        session=db_session, symbol="AAPL", items=items, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
