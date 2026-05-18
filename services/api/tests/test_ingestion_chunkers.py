import hashlib
from dataclasses import FrozenInstanceError

import pytest


def test_chunk_draft_is_frozen_dataclass() -> None:
    from app.services.ingestion._chunkers import ChunkDraft

    draft = ChunkDraft(
        chunk_index=0,
        text="hello",
        start_offset=None,
        end_offset=None,
        attributes={},
        content_hash=hashlib.sha256(b"hello").hexdigest(),
    )
    with pytest.raises(FrozenInstanceError):
        draft.text = "world"  # type: ignore[misc]


def test_chunk_fred_observations_emits_one_chunk_per_observation() -> None:
    from datetime import date
    from decimal import Decimal

    from app.services.ingestion._chunkers import chunk_fred_observations
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations

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

    chunks = chunk_fred_observations(payload)

    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert "GDP" in chunks[0].text
    assert "2024-01-01" in chunks[0].text
    assert "100.5" in chunks[0].text
    assert chunks[0].attributes["date"] == "2024-01-01"
    assert chunks[1].attributes["date"] == "2024-02-01"
    assert chunks[1].attributes["value"] is None


def test_chunk_sec_tickers_emits_one_chunk_per_company() -> None:
    from app.services.ingestion._chunkers import chunk_sec_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft Corp"),
        ]
    )

    chunks = chunk_sec_tickers(payload)

    assert len(chunks) == 2
    assert "AAPL" in chunks[0].text
    assert "Apple Inc." in chunks[0].text
    assert chunks[0].attributes["cik"] == "0000320193"
    assert chunks[0].attributes["ticker"] == "AAPL"


def test_chunk_sec_submissions_emits_one_chunk_per_filing() -> None:
    from datetime import date

    from app.services.ingestion._chunkers import chunk_sec_submissions
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
            SecRecentSubmission(
                accession_number="0000320193-24-000002",
                filing_date=date(2024, 5, 1),
                report_date=None,
                form="8-K",
                primary_document="aapl-8k.htm",
                primary_doc_description=None,
            ),
        ],
    )

    chunks = chunk_sec_submissions(payload)

    assert len(chunks) == 2
    assert "10-K" in chunks[0].text
    assert chunks[0].attributes["accession_number"] == "0000320193-24-000001"
    assert chunks[0].attributes["form"] == "10-K"
    assert chunks[1].attributes["form"] == "8-K"
    assert chunks[1].attributes["report_date"] is None


def test_chunk_fred_observations_returns_empty_for_no_observations() -> None:
    from datetime import date

    from app.services.ingestion._chunkers import chunk_fred_observations
    from app.services.source_clients.fred import FredSeriesObservations

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 1, 1),
        count=0,
        observations=[],
    )

    assert chunk_fred_observations(payload) == []


def test_chunk_fred_observations_is_deterministic() -> None:
    from datetime import date
    from decimal import Decimal

    from app.services.ingestion._chunkers import chunk_fred_observations
    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )

    payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2024, 1, 1),
                value=Decimal("310.328"),
                realtime_start=date(2024, 2, 1),
                realtime_end=date(2024, 12, 31),
            ),
        ],
    )

    first = chunk_fred_observations(payload)
    second = chunk_fred_observations(payload)

    assert [draft.text for draft in first] == [draft.text for draft in second]
    assert [draft.content_hash for draft in first] == [
        draft.content_hash for draft in second
    ]


def test_chunk_sec_submissions_returns_empty_for_no_recent_filings() -> None:
    from app.services.ingestion._chunkers import chunk_sec_submissions
    from app.services.source_clients.sec_edgar import SecSubmissionsResponse

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic=None,
        tickers=[],
        recent=[],
    )

    assert chunk_sec_submissions(payload) == []


def test_chunker_content_hashes_are_sha256_of_chunk_text() -> None:
    from datetime import date

    from app.services.ingestion._chunkers import chunk_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic=None,
        tickers=[],
        recent=[
            SecRecentSubmission(
                accession_number="acc-1",
                filing_date=date(2024, 1, 1),
                report_date=None,
                form="10-K",
                primary_document="a.htm",
                primary_doc_description=None,
            ),
        ],
    )

    chunks = chunk_sec_submissions(payload)
    assert chunks[0].content_hash == hashlib.sha256(chunks[0].text.encode("utf-8")).hexdigest()
