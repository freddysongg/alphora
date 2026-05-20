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
    assert chunks[0].attributes["source"] == "tiingo_news"
    assert chunks[0].attributes["outlet"] == "Reuters"
    assert chunks[0].attributes["tickers"] == ["spy"]


def test_chunk_polymarket_price_history_emits_one_chunk_per_point() -> None:
    from app.services.ingestion._chunkers import chunk_polymarket_price_history
    from app.services.source_clients.polymarket_data import (
        PolymarketPriceHistory,
        PolymarketPricePoint,
    )

    payload = PolymarketPriceHistory(
        market="m1",
        interval="1d",
        history=[
            PolymarketPricePoint(t=1714521600, p=0.42, v=100.0),
            PolymarketPricePoint(t=1714608000, p=0.43, v=200.0),
        ],
    )
    chunks = chunk_polymarket_price_history(payload)

    assert len(chunks) == 2
    assert chunks[0].attributes["market"] == "m1"
    assert chunks[0].attributes["interval"] == "1d"
    assert chunks[0].attributes["probability"] == 0.42
    assert chunks[0].attributes["volume_usd"] == 100.0
    assert chunks[0].content_hash != chunks[1].content_hash


def test_chunk_finnhub_news_emits_one_chunk_per_item() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_finnhub_news
    from app.services.source_clients.finnhub import FinnhubNewsItem

    items = [
        FinnhubNewsItem(
            id=1,
            category="company",
            headline="h1",
            summary="s1",
            source="src",
            url="https://x",
            related="AAPL",
            published_at=datetime(2026, 5, 15, tzinfo=UTC),
        ),
        FinnhubNewsItem(
            id=2,
            category="company",
            headline="h2",
            summary=None,
            source="src",
            url="https://y",
            related=None,
            published_at=datetime(2026, 5, 16, tzinfo=UTC),
        ),
    ]
    chunks = chunk_finnhub_news(items)

    assert len(chunks) == 2
    assert chunks[0].attributes["source"] == "finnhub_news"
    assert chunks[0].attributes["news_id"] == 1
    assert chunks[0].attributes["related"] == "AAPL"
    assert chunks[1].attributes["summary"] is None
    assert "none" in chunks[1].text


def test_chunk_cme_fedwatch_emits_one_chunk_per_probability() -> None:
    from datetime import UTC, date, datetime

    from app.services.ingestion._chunkers import chunk_cme_fedwatch
    from app.services.source_clients.cme_fedwatch import (
        FedWatchMeeting,
        FedWatchProbability,
    )

    meeting = FedWatchMeeting(
        as_of=datetime(2026, 5, 19, tzinfo=UTC),
        meeting_date=date(2026, 6, 17),
        current_target_low_bps=425,
        current_target_high_bps=450,
        probabilities=[
            FedWatchProbability(target_low_bps=400, target_high_bps=425, probability=0.3),
            FedWatchProbability(target_low_bps=425, target_high_bps=450, probability=0.6),
            FedWatchProbability(target_low_bps=450, target_high_bps=475, probability=0.1),
        ],
    )
    chunks = chunk_cme_fedwatch(meeting)

    assert len(chunks) == 3
    assert chunks[0].attributes["meeting_date"] == "2026-06-17"
    assert chunks[0].attributes["target_low_bps"] == 400
    assert chunks[0].attributes["probability"] == 0.3
    assert chunks[1].attributes["target_low_bps"] == 425


def test_chunk_fed_press_emits_one_chunk_per_item() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_fed_press
    from app.services.source_clients.fed_press import FedPressItem

    items = [
        FedPressItem(
            id="monetary20260507a",
            kind="monetary",
            title="FOMC statement",
            url="https://www.federalreserve.gov/x",
            published_at=datetime(2026, 5, 7, 18, tzinfo=UTC),
            summary="held rates",
        ),
        FedPressItem(
            id="powell20260512a",
            kind="speech",
            title="Outlook",
            url="https://www.federalreserve.gov/y",
            published_at=datetime(2026, 5, 12, 13, tzinfo=UTC),
            speaker="Jerome H. Powell",
            venue="CFR",
            summary=None,
        ),
    ]
    chunks = chunk_fed_press(items)

    assert len(chunks) == 2
    assert chunks[0].attributes["kind"] == "monetary"
    assert chunks[1].attributes["kind"] == "speech"
    assert chunks[1].attributes["speaker"] == "Jerome H. Powell"
    assert "n/a" in chunks[0].text  # speaker missing on monetary release


def test_chunk_gdelt_articles_emits_one_chunk_per_article() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion._chunkers import chunk_gdelt_articles
    from app.services.source_clients.gdelt import GdeltArticle

    articles = [
        GdeltArticle(
            url="https://x",
            title="t1",
            seendate=datetime(2026, 5, 1, tzinfo=UTC),
            domain="reuters.com",
            language="English",
            sourcecountry="US",
            tone=-1.5,
            themes=["TRADE", "GEOPOLITICS"],
        ),
        GdeltArticle(
            url="https://y",
            title="t2",
            seendate=datetime(2026, 5, 2, tzinfo=UTC),
            tone=2.0,
        ),
    ]
    chunks = chunk_gdelt_articles(articles)

    assert len(chunks) == 2
    assert chunks[0].attributes["url"] == "https://x"
    assert chunks[0].attributes["themes"] == ["TRADE", "GEOPOLITICS"]
    assert chunks[0].attributes["tone"] == -1.5
    assert chunks[1].attributes["themes"] == []
    assert "none" in chunks[1].text  # empty themes formatted as "none"
