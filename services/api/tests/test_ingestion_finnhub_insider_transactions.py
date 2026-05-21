import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_insider_transactions import (
    ingest_finnhub_insider_transactions,
)
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransaction,
    FinnhubInsiderTransactionsResponse,
)


def _response() -> FinnhubInsiderTransactionsResponse:
    return FinnhubInsiderTransactionsResponse(
        symbol="AAPL",
        data=[
            FinnhubInsiderTransaction(
                name="Tim Cook",
                share=1000,
                change=-500,
                filing_date=date(2026, 5, 15),
                transaction_date=date(2026, 5, 13),
                transaction_code="S",
                transaction_price=195.5,
            ),
            FinnhubInsiderTransaction(
                name="Luca Maestri",
                share=200,
                change=200,
                filing_date=date(2026, 5, 10),
                transaction_date=date(2026, 5, 8),
                transaction_code="P",
                transaction_price=192.0,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_ingest_finnhub_insider_transactions_writes_one_chunk_per_row(
    db_session: AsyncSession,
) -> None:
    response = _response()
    body = json.dumps(response.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    assert result.source == "finnhub_insider_transactions"
    assert result.chunk_count == 2

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    chunks_sorted = sorted(chunks, key=lambda c: c.chunk_index)
    assert "Tim Cook" in chunks_sorted[0].text
    assert chunks_sorted[0].attributes["transaction_code"] == "S"
    assert chunks_sorted[0].attributes["change"] == -500
    assert chunks_sorted[0].attributes["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_insider_transactions_is_idempotent(
    db_session: AsyncSession,
) -> None:
    response = _response()
    body = json.dumps(response.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
