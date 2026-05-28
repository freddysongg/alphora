from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.fetchers import (
    MAX_PREVIEW_ROWS,
    MAX_RAW_BYTES,
    fetch_finnhub_news,
)


@pytest.mark.asyncio
async def test_finnhub_news_projects_to_preview_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.source_clients import finnhub as finnhub_client
    from app.services.source_clients.finnhub import FinnhubNewsItem

    items = [
        FinnhubNewsItem(
            id=1,
            category="company",
            headline="big news",
            summary=None,
            source="reuters",
            url="https://example.com/1",
            image=None,
            related="AAPL",
            published_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
    ]
    mock_fetch = AsyncMock(return_value=(items, "hash"))
    monkeypatch.setattr(finnhub_client, "fetch_finnhub_company_news", mock_fetch)

    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_news(client=client, ticker="AAPL", lookback_days=30)

    assert payload.rows == [
        {
            "headline": "big news",
            "source": "reuters",
            "published_at": "2026-05-27T00:00:00+00:00",
        }
    ]
    assert payload.as_of == datetime(2026, 5, 27, tzinfo=UTC)
    assert len(payload.raw.encode()) <= MAX_RAW_BYTES


@pytest.mark.asyncio
async def test_finnhub_news_truncates_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.source_clients import finnhub as finnhub_client
    from app.services.source_clients.finnhub import FinnhubNewsItem

    items = [
        FinnhubNewsItem(
            id=i,
            category="company",
            headline=f"h{i}",
            source="src",
            url=f"https://example.com/{i}",
            related="AAPL",
            published_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
        for i in range(MAX_PREVIEW_ROWS + 50)
    ]
    monkeypatch.setattr(
        finnhub_client,
        "fetch_finnhub_company_news",
        AsyncMock(return_value=(items, "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_news(client=client, ticker="AAPL", lookback_days=30)
    assert len(payload.rows) == MAX_PREVIEW_ROWS


@pytest.mark.asyncio
async def test_finnhub_news_empty_returns_none_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.source_clients import finnhub as finnhub_client

    monkeypatch.setattr(
        finnhub_client,
        "fetch_finnhub_company_news",
        AsyncMock(return_value=([], "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_news(client=client, ticker="AAPL", lookback_days=30)
    assert payload.rows == []
    assert payload.as_of is None


@pytest.mark.asyncio
async def test_finnhub_peers_projects_to_peer_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.data_sources.fetchers import fetch_finnhub_peers
    from app.services.source_clients import finnhub as finnhub_client

    monkeypatch.setattr(
        finnhub_client,
        "fetch_finnhub_peers",
        AsyncMock(return_value=(["MSFT", "GOOGL"], "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_peers(client=client, ticker="AAPL")
    assert payload.rows == [{"peer": "MSFT"}, {"peer": "GOOGL"}]
    assert payload.as_of is None


@pytest.mark.asyncio
async def test_congress_bills_projects_correct_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.data_sources.fetchers import fetch_congress_bills
    from app.services.source_clients import congress_gov as congress_gov_client
    from app.services.source_clients.congress_gov import CongressBill, CongressBillsResponse

    update_dt = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    bills_response = CongressBillsResponse(
        bills=[
            CongressBill(
                congress=119,
                type="HR",
                number="1234",
                title="A Test Bill",
                updateDate=update_dt,
            )
        ]
    )
    monkeypatch.setattr(
        congress_gov_client,
        "fetch_congress_bills",
        AsyncMock(return_value=(bills_response, "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_congress_bills(client=client)

    assert payload.rows == [
        {
            "congress": 119,
            "number": "1234",
            "title": "A Test Bill",
            "updateDate": "2026-05-01T12:00:00+00:00",
        }
    ]
    assert payload.as_of == update_dt


@pytest.mark.asyncio
async def test_polymarket_events_projects_correct_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.data_sources.fetchers import fetch_polymarket_events
    from app.services.source_clients import polymarket as polymarket_client
    from app.services.source_clients.polymarket import PolymarketEvent

    events = [
        PolymarketEvent(
            id="abc123",
            slug="will-fed-cut-rates",
            title="Will Fed cut rates?",
            active=True,
            closed=False,
            category="economics",
        )
    ]
    monkeypatch.setattr(
        polymarket_client,
        "fetch_polymarket_events",
        AsyncMock(return_value=(events, "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_polymarket_events(client=client)

    assert payload.rows == [
        {
            "slug": "will-fed-cut-rates",
            "title": "Will Fed cut rates?",
            "category": "economics",
            "active": True,
        }
    ]
    assert payload.as_of is None


def test_truncate_raw_returns_valid_json_placeholder_when_oversized() -> None:
    import json

    from app.services.data_sources.fetchers import MAX_RAW_BYTES, _truncate_raw

    payload = ["x" * 1000 for _ in range(500)]
    raw = _truncate_raw(payload)
    parsed = json.loads(raw)
    assert parsed.get("truncated") is True
    assert isinstance(parsed.get("approximate_byte_size"), int)
    assert len(raw.encode()) <= MAX_RAW_BYTES
