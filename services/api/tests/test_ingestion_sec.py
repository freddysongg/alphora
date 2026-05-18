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


async def test_ingest_sec_company_tickers_persists_one_evidence_with_chunks_per_company(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_company_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft"),
        ]
    )
    content_hash = hashlib.sha256(b"tickers-body").hexdigest()

    result = await ingest_sec_company_tickers(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url="https://www.sec.gov/files/company_tickers.json",
    )

    assert result.source == "sec_edgar"
    assert result.document_id == "company_tickers"
    assert result.chunk_count == 2


async def test_ingest_sec_company_tickers_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_company_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
        ]
    )
    content_hash = hashlib.sha256(b"tickers-body-2").hexdigest()

    first = await ingest_sec_company_tickers(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_sec_company_tickers(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
    assert second.chunk_count == first.chunk_count == 1


async def test_ingest_sec_submissions_uses_cik_as_document_id(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic="3571",
        tickers=["AAPL"],
        recent=[
            SecRecentSubmission(
                accession_number="0000320193-24-000001",
                filing_date=date(2024, 2, 1),
                report_date=date(2023, 12, 31),
                form="10-K",
                primary_document="aapl-20231231.htm",
                primary_doc_description="10-K",
            ),
        ],
    )
    content_hash = hashlib.sha256(b"submissions-body").hexdigest()

    result = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert result.source == "sec_edgar"
    assert result.document_id == "submissions|0000320193"
    assert result.chunk_count == 1


async def test_ingest_sec_submissions_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_submissions
    from app.services.source_clients.sec_edgar import SecSubmissionsResponse

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic=None,
        tickers=[],
        recent=[],
    )
    content_hash = hashlib.sha256(b"empty-submissions").hexdigest()

    first = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
    assert second.chunk_count == 0


async def test_ingest_sec_company_tickers_stores_structured_payload(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import Evidence
    from app.services.ingestion.sec_filings import ingest_sec_company_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
        ]
    )
    content_hash = hashlib.sha256(b"structured-tickers").hexdigest()

    result = await ingest_sec_company_tickers(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url="https://www.sec.gov/files/company_tickers.json",
    )

    persisted = (
        (
            await populated_session.execute(
                select(Evidence).where(Evidence.id == result.evidence_id)
            )
        )
        .scalars()
        .one()
    )

    assert persisted.structured == {
        "companies": [
            {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        ]
    }
    assert persisted.raw_url == "https://www.sec.gov/files/company_tickers.json"


async def test_ingest_sec_submissions_writes_chunks_with_form_attributes(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import EvidenceChunk
    from app.services.ingestion.sec_filings import ingest_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000789019",
        name="Microsoft Corp",
        sic="7372",
        tickers=["MSFT"],
        recent=[
            SecRecentSubmission(
                accession_number="0000789019-24-000005",
                filing_date=date(2024, 4, 15),
                report_date=None,
                form="8-K",
                primary_document="msft-8k.htm",
                primary_doc_description=None,
            ),
        ],
    )
    content_hash = hashlib.sha256(b"msft-submissions").hexdigest()

    result = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    chunks = (
        (
            await populated_session.execute(
                select(EvidenceChunk)
                .where(EvidenceChunk.evidence_id == result.evidence_id)
                .order_by(EvidenceChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )

    assert len(chunks) == 1
    assert chunks[0].attributes is not None
    assert chunks[0].attributes["form"] == "8-K"
    assert chunks[0].attributes["cik"] == "0000789019"
    assert chunks[0].attributes["report_date"] is None
