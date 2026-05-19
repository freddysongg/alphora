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


def test_chunk_polymarket_events_emits_one_chunk_per_event() -> None:
    from app.services.ingestion._chunkers import chunk_polymarket_events
    from app.services.source_clients.polymarket import PolymarketEvent

    events = [
        PolymarketEvent(
            id="e1",
            slug="fed-cuts-2026",
            title="Fed cuts in 2026",
            active=True,
            closed=False,
            category="economics",
        ),
        PolymarketEvent(
            id="e2",
            slug="recession-2026",
            title="US recession 2026",
            active=True,
            closed=False,
            category="economics",
        ),
    ]
    chunks = chunk_polymarket_events(events)
    assert len(chunks) == 2
    assert "Fed cuts in 2026" in chunks[0].text
    assert chunks[0].attributes["event_id"] == "e1"
    assert chunks[0].content_hash != chunks[1].content_hash


def test_chunk_kalshi_markets_emits_one_chunk_per_market() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_kalshi_markets
    from app.services.source_clients.kalshi import KalshiMarket

    markets = [
        KalshiMarket(
            ticker="FED-2026",
            event_ticker="FED",
            title="Fed cuts in 2026",
            status="open",
            open_time=datetime(2026, 1, 1, tzinfo=UTC),
            close_time=datetime(2026, 12, 31, tzinfo=UTC),
            yes_bid=42,
            yes_ask=45,
            volume=1000,
        ),
    ]
    chunks = chunk_kalshi_markets(markets)
    assert len(chunks) == 1
    assert chunks[0].attributes["ticker"] == "FED-2026"


def test_chunk_congress_bills_emits_one_chunk_per_bill() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_congress_bills
    from app.services.source_clients.congress_gov import CongressBill

    bills = [
        CongressBill(
            congress=119,
            type="HR",
            number="1234",
            title="A bill to do X",
            updateDate=datetime(2026, 4, 15, tzinfo=UTC),
        ),
    ]
    chunks = chunk_congress_bills(bills)
    assert len(chunks) == 1
    assert chunks[0].attributes["number"] == "1234"


def test_chunk_tiingo_news_items_emits_one_chunk_per_article() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_tiingo_news_items
    from app.services.source_clients.tiingo_news import TiingoNewsItem

    items = [
        TiingoNewsItem(
            id=1,
            title="Fed holds rates",
            description="FOMC decision",
            url="https://example.com",
            publishedDate=datetime(2026, 5, 18, 14, 0, tzinfo=UTC),
            source="Reuters",
            tickers=["spy"],
            tags=["fed"],
        ),
    ]
    chunks = chunk_tiingo_news_items(items)
    assert len(chunks) == 1
    assert chunks[0].attributes["source"] == "Reuters"
    assert chunks[0].attributes["tickers"] == ["spy"]
