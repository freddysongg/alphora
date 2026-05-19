import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.congress_bills import ingest_congress_bills
from app.services.source_clients.congress_gov import CongressBill


def _bills() -> list[CongressBill]:
    return [
        CongressBill(
            congress=119,
            type="HR",
            number="100",
            title="Bill A",
            updateDate=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        CongressBill(
            congress=119,
            type="S",
            number="50",
            title="Bill B",
            updateDate=datetime(2026, 2, 2, tzinfo=UTC),
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_congress_bills_writes_two_chunks(db_session: AsyncSession) -> None:
    bills = _bills()
    body = json.dumps([b.model_dump(mode="json") for b in bills], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_congress_bills(
        session=db_session, bills=bills, content_hash=h, raw_url=None
    )
    assert result.source == "congress_bills"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_congress_bills_is_idempotent(db_session: AsyncSession) -> None:
    bills = _bills()
    body = json.dumps([b.model_dump(mode="json") for b in bills], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_congress_bills(session=db_session, bills=bills, content_hash=h, raw_url=None)
    b = await ingest_congress_bills(session=db_session, bills=bills, content_hash=h, raw_url=None)
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
