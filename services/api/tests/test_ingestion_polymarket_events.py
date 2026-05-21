import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion.polymarket_events import ingest_polymarket_events
from app.services.source_clients.polymarket import PolymarketEvent


def _events() -> list[PolymarketEvent]:
    return [
        PolymarketEvent(id="e1", slug="x", title="x", active=True, closed=False, category="econ"),
        PolymarketEvent(id="e2", slug="y", title="y", active=True, closed=False, category="econ"),
    ]


@pytest.mark.asyncio
async def test_ingest_polymarket_events_writes_evidence_and_chunks(
    db_session: AsyncSession,
) -> None:
    events = _events()
    body = json.dumps([e.model_dump(mode="json") for e in events]).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    result = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url="https://gamma-api.polymarket.com/events",
    )

    assert result.source == "polymarket_events"
    assert result.chunk_count == 2
    evidence = (await db_session.execute(select(Evidence))).scalars().all()
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(evidence) == 1
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_ingest_polymarket_events_is_idempotent(
    db_session: AsyncSession,
) -> None:
    events = _events()
    body = json.dumps([e.model_dump(mode="json") for e in events]).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    first = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url=None,
    )

    assert first.evidence_id == second.evidence_id
    assert first.chunk_count == second.chunk_count == 2
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
