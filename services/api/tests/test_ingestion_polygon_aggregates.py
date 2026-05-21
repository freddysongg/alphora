import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion.polygon_aggregates import ingest_polygon_aggregates
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)


def _payload() -> PolygonAggregatesResponse:
    return PolygonAggregatesResponse(
        ticker="XLK",
        queryCount=2,
        resultsCount=2,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(o=100.0, c=101.0, h=102.0, l=99.5, v=1000.0, t=1715040000000),
            PolygonAggregateBar(o=101.0, c=103.0, h=103.5, l=100.0, v=1500.0, t=1715126400000),
        ],
    )


@pytest.mark.asyncio
async def test_ingest_polygon_aggregates_writes_evidence_and_chunks(
    db_session: AsyncSession,
) -> None:
    payload = _payload()
    body = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    result = await ingest_polygon_aggregates(
        session=db_session,
        payload=payload,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 2),
        multiplier=1,
        timespan="day",
        content_hash=content_hash,
        raw_url=None,
    )

    assert result.source == "polygon_aggregates"
    assert result.chunk_count == 2
    evidence = (await db_session.execute(select(Evidence))).scalars().all()
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(evidence) == 1
    assert len(chunks) == 2
    assert evidence[0].source == "polygon_aggregates"


@pytest.mark.asyncio
async def test_ingest_polygon_aggregates_is_idempotent(
    db_session: AsyncSession,
) -> None:
    payload = _payload()
    body = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    first = await ingest_polygon_aggregates(
        session=db_session,
        payload=payload,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 2),
        multiplier=1,
        timespan="day",
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_polygon_aggregates(
        session=db_session,
        payload=payload,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 2),
        multiplier=1,
        timespan="day",
        content_hash=content_hash,
        raw_url=None,
    )

    assert first.evidence_id == second.evidence_id
    assert first.chunk_count == second.chunk_count == 2
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_chunk_attributes_contain_ohlcv(
    db_session: AsyncSession,
) -> None:
    payload = _payload()
    body = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    await ingest_polygon_aggregates(
        session=db_session,
        payload=payload,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 2),
        multiplier=1,
        timespan="day",
        content_hash=content_hash,
        raw_url=None,
    )

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    chunk_attrs = chunks[0].attributes
    assert isinstance(chunk_attrs, dict)
    assert chunk_attrs["ticker"] == "XLK"
    assert chunk_attrs["open"] == 100.0
    assert chunk_attrs["close"] == 101.0
    assert chunk_attrs["volume"] == 1000.0
