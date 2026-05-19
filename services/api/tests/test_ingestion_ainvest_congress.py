import hashlib
from collections.abc import AsyncIterator
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


def _payload() -> "object":
    from app.services.source_clients.ainvest import (
        AinvestCongressData,
        AinvestCongressResponse,
        AinvestCongressTransaction,
    )

    return AinvestCongressResponse(
        data=AinvestCongressData(
            data=[
                AinvestCongressTransaction(
                    name="Jane Doe",
                    party="D",
                    state="CA",
                    trade_date=date(2026, 4, 1),
                    filing_date=date(2026, 4, 15),
                    reporting_gap="14 days",
                    trade_type="purchase",
                    size="$1,001 - $15,000",
                ),
            ]
        ),
        status_code=200,
        status_msg="ok",
    )


async def test_ingest_ainvest_congress_persists_one_chunk_per_transaction(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.ainvest_congress import (
        ingest_ainvest_congress_transactions,
    )

    content_hash = hashlib.sha256(b"ainvest-body").hexdigest()
    result = await ingest_ainvest_congress_transactions(
        session=populated_session,
        ticker="AAPL",
        payload=_payload(),  # type: ignore[arg-type]
        content_hash=content_hash,
        raw_url="https://openapi.ainvest.com/open/ownership/congress",
    )

    assert result.source == "ainvest_congress"
    assert result.document_id.startswith("ainvest_congress|AAPL|")
    assert result.chunk_count == 1


async def test_ingest_ainvest_congress_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.ainvest_congress import (
        ingest_ainvest_congress_transactions,
    )

    content_hash = hashlib.sha256(b"ainvest-body-2").hexdigest()
    first = await ingest_ainvest_congress_transactions(
        session=populated_session,
        ticker="AAPL",
        payload=_payload(),  # type: ignore[arg-type]
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_ainvest_congress_transactions(
        session=populated_session,
        ticker="AAPL",
        payload=_payload(),  # type: ignore[arg-type]
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
    assert second.chunk_count == first.chunk_count == 1
