import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_peers import ingest_finnhub_peers


@pytest.mark.asyncio
async def test_ingest_finnhub_peers_writes_single_chunk_with_structured_peers(
    db_session: AsyncSession,
) -> None:
    peers = ["MSFT", "GOOGL", "AMZN", "META"]
    body = json.dumps(peers).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    assert result.source == "finnhub_peers"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert "MSFT, GOOGL, AMZN, META" in chunks[0].text
    assert chunks[0].attributes["peers"] == ["MSFT", "GOOGL", "AMZN", "META"]
    assert chunks[0].attributes["for_ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_peers_is_idempotent(
    db_session: AsyncSession,
) -> None:
    peers = ["MSFT", "GOOGL"]
    body = json.dumps(peers).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
