import hashlib
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_ingest_fred_persists_evidence_and_chunks(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.fred_observations import (
        ingest_fred_series_observations,
    )
    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 3, 1),
        count=2,
        observations=[
            FredObservation(
                date=date(2024, 1, 1),
                value=Decimal("100.5"),
                realtime_start=date(2024, 1, 15),
                realtime_end=date(2024, 12, 31),
            ),
            FredObservation(
                date=date(2024, 2, 1),
                value=None,
                realtime_start=date(2024, 2, 15),
                realtime_end=date(2024, 12, 31),
            ),
        ],
    )
    content_hash = hashlib.sha256(b"raw-body").hexdigest()

    result = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url="https://api.stlouisfed.org/fred/series/observations?...",
    )

    assert result.source == "fred"
    assert result.document_id == "GDP|2024-01-01|2024-03-01"
    assert result.content_hash == content_hash
    assert result.chunk_count == 2


async def test_ingest_fred_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.fred_observations import (
        ingest_fred_series_observations,
    )
    from app.services.source_clients.fred import FredSeriesObservations

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 3, 1),
        count=0,
        observations=[],
    )
    content_hash = hashlib.sha256(b"raw-body-2").hexdigest()

    first = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
    assert second.chunk_count == first.chunk_count
    assert second.chunk_count == 0


async def test_ingest_fred_writes_chunks_with_observation_attributes(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import EvidenceChunk
    from app.services.ingestion.fred_observations import (
        ingest_fred_series_observations,
    )
    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )

    payload = FredSeriesObservations(
        series_id="UNRATE",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2024, 1, 1),
                value=Decimal("3.7"),
                realtime_start=date(2024, 2, 1),
                realtime_end=date(2024, 12, 31),
            ),
        ],
    )
    content_hash = hashlib.sha256(b"unrate-body").hexdigest()

    result = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    chunks = (
        (
            await populated_session.execute(
                select(EvidenceChunk).where(
                    EvidenceChunk.evidence_id == result.evidence_id
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(chunks) == 1
    assert chunks[0].attributes is not None
    assert chunks[0].attributes["series_id"] == "UNRATE"
    assert chunks[0].attributes["date"] == "2024-01-01"
