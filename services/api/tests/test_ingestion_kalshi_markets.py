import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion.kalshi_markets import ingest_kalshi_markets
from app.services.source_clients.kalshi import KalshiMarket


def _markets() -> list[KalshiMarket]:
    return [
        KalshiMarket(
            ticker="FED-25",
            event_ticker="FED",
            title="Fed in 2025",
            status="open",
            yes_bid=10,
            yes_ask=20,
            open_time=datetime(2025, 1, 1, tzinfo=UTC),
            close_time=datetime(2025, 12, 31, tzinfo=UTC),
            volume=0,
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_kalshi_markets_writes_evidence_and_chunks(
    db_session: AsyncSession,
) -> None:
    markets = _markets()
    body = json.dumps(
        [m.model_dump(mode="json") for m in markets], default=str
    ).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    result = await ingest_kalshi_markets(
        session=db_session,
        markets=markets,
        content_hash=content_hash,
        raw_url=None,
    )

    assert result.source == "kalshi_markets"
    assert result.chunk_count == 1
    evidence = (await db_session.execute(select(Evidence))).scalars().all()
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(evidence) == 1
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_ingest_kalshi_markets_is_idempotent(
    db_session: AsyncSession,
) -> None:
    markets = _markets()
    body = json.dumps(
        [m.model_dump(mode="json") for m in markets], default=str
    ).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    first = await ingest_kalshi_markets(
        session=db_session,
        markets=markets,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_kalshi_markets(
        session=db_session,
        markets=markets,
        content_hash=content_hash,
        raw_url=None,
    )

    assert first.evidence_id == second.evidence_id
    assert first.chunk_count == second.chunk_count == 1
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
