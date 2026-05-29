"""Per-source dry-run fetchers.

Each function:
1. Calls the existing source-client function from `app.services.source_clients`.
2. Projects the parsed model to the source's `preview_columns`.
3. Truncates the row list and the raw JSON byte size.
4. Returns a `TestPullPayload`.

These fetchers DO NOT touch anything in `app.services.ingestion` — the
intent is to exercise the live API without writing to the evidence chunk
tables.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from app.config import get_settings
from app.services.source_clients import (
    cme_fedwatch as cme_fedwatch_client,
)
from app.services.source_clients import (
    congress_gov as congress_gov_client,
)
from app.services.source_clients import (
    fed_press as fed_press_client,
)
from app.services.source_clients import (
    finnhub as finnhub_client,
)
from app.services.source_clients import (
    fred as fred_client,
)
from app.services.source_clients import (
    gdelt as gdelt_client,
)
from app.services.source_clients import (
    kalshi as kalshi_client,
)
from app.services.source_clients import (
    polygon as polygon_client,
)
from app.services.source_clients import (
    polymarket as polymarket_client,
)
from app.services.source_clients import (
    polymarket_data as polymarket_data_client,
)
from app.services.source_clients import (
    sec_edgar as sec_edgar_client,
)
from app.services.source_clients import (
    tiingo_news as tiingo_news_client,
)
from app.services.source_clients._http import SourceClientConfigError

MAX_PREVIEW_ROWS: int = 200
MAX_RAW_BYTES: int = 256 * 1024
DEFAULT_FRED_SERIES: str = "GDP"


@dataclass(frozen=True)
class TestPullPayload:
    rows: list[dict[str, object]]
    raw: str
    as_of: datetime | None


def _today() -> date:
    return datetime.now(UTC).date()


def _truncate_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return rows[:MAX_PREVIEW_ROWS]


def _truncate_raw(raw: object) -> str:
    blob = json.dumps(raw, default=str)
    if len(blob.encode()) <= MAX_RAW_BYTES:
        return blob
    return json.dumps(
        {
            "truncated": True,
            "approximate_byte_size": len(blob.encode()),
        }
    )


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


async def fetch_finnhub_news(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    items, _ = await finnhub_client.fetch_finnhub_company_news(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    rows = _truncate_rows(
        [
            {
                "headline": item.headline,
                "source": item.source,
                "published_at": _iso(item.published_at),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    as_of = max((item.published_at for item in items), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_finnhub_insider_transactions(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    response, _ = await finnhub_client.fetch_finnhub_insider_transactions(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    rows = _truncate_rows(
        [
            {
                "name": tx.name,
                "share": tx.share,
                "change": tx.change,
                "transaction_date": _iso(tx.transaction_date),
                "transaction_code": tx.transaction_code,
                "transaction_price": tx.transaction_price,
            }
            for tx in response.data
        ]
    )
    raw = _truncate_raw([tx.model_dump(mode="json") for tx in response.data])
    as_of = max((datetime.combine(tx.transaction_date, datetime.min.time(), tzinfo=UTC) for tx in response.data), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_finnhub_peers(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    peers, _ = await finnhub_client.fetch_finnhub_peers(client=client, symbol=ticker)
    rows = _truncate_rows([{"peer": peer} for peer in peers])
    raw = _truncate_raw(peers)
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_finnhub_price_target(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    target, _ = await finnhub_client.fetch_finnhub_price_target(client=client, symbol=ticker)
    rows = [
        {
            "target_low": target.target_low,
            "target_mean": target.target_mean,
            "target_median": target.target_median,
            "target_high": target.target_high,
            "number_of_analysts": target.number_of_analysts,
            "last_updated": _iso(target.last_updated),
        }
    ]
    raw = _truncate_raw(target.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=target.last_updated)


async def fetch_finnhub_profile(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    profile, _ = await finnhub_client.fetch_finnhub_profile(client=client, symbol=ticker)
    rows = [
        {
            "name": profile.name,
            "exchange": profile.exchange,
            "finnhub_industry": profile.finnhub_industry,
            "market_capitalization": profile.market_capitalization,
            "share_outstanding": profile.share_outstanding,
        }
    ]
    raw = _truncate_raw(profile.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_finnhub_recommendation(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    items, _ = await finnhub_client.fetch_finnhub_recommendation(client=client, symbol=ticker)
    rows = _truncate_rows(
        [
            {
                "period": _iso(item.period),
                "strong_buy": item.strong_buy,
                "buy": item.buy,
                "hold": item.hold,
                "sell": item.sell,
                "strong_sell": item.strong_sell,
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    as_of = max(
        (datetime.combine(item.period, datetime.min.time(), tzinfo=UTC) for item in items),
        default=None,
    )
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_polygon_aggregates(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    response, _ = await polygon_client.fetch_polygon_aggregates(
        client=client,
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_date=from_date,
        to_date=to_date,
    )
    rows = _truncate_rows(
        [
            {
                "timestamp_ms": bar.timestamp_ms,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in response.results
        ]
    )
    raw = _truncate_raw([bar.model_dump(mode="json") for bar in response.results])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_sec_filings(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    tickers_response, _ = await sec_edgar_client.fetch_company_tickers(client=client)
    cik_str: str | None = None
    for company in tickers_response.companies:
        if company.ticker.upper() == ticker.upper():
            cik_str = str(company.cik_str)
            break
    if cik_str is None:
        return TestPullPayload(rows=[], raw="[]", as_of=None)

    submissions, _ = await sec_edgar_client.fetch_submissions(client=client, cik=cik_str)
    rows = _truncate_rows(
        [
            {
                "form": filing.form,
                "filing_date": _iso(filing.filing_date),
                "accession_number": filing.accession_number,
                "primary_document": filing.primary_document,
            }
            for filing in submissions.recent
        ]
    )
    raw = _truncate_raw([filing.model_dump(mode="json") for filing in submissions.recent])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_tiingo_news_items(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    items, _ = await tiingo_news_client.fetch_tiingo_news(
        client=client, tickers=[ticker], limit=MAX_PREVIEW_ROWS
    )
    rows = _truncate_rows(
        [
            {
                "title": item.title,
                "source": item.source,
                "publishedDate": _iso(item.publishedDate),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    as_of = max((item.publishedDate for item in items), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_gdelt(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    response, _ = await gdelt_client.fetch_gdelt_articles(client=client, query=ticker)
    rows = _truncate_rows(
        [
            {
                "title": article.title,
                "domain": article.domain,
                "seendate": _iso(article.seendate),
            }
            for article in response.articles
        ]
    )
    raw = _truncate_raw([article.model_dump(mode="json") for article in response.articles])
    as_of = max((article.seendate for article in response.articles), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_fred_observations(*, client: httpx.AsyncClient) -> TestPullPayload:
    result, _ = await fred_client.fetch_series_observations(
        client=client, series_id=DEFAULT_FRED_SERIES
    )
    rows = _truncate_rows(
        [
            {
                "date": _iso(obs.date),
                "value": str(obs.value) if obs.value is not None else None,
            }
            for obs in result.observations
        ]
    )
    raw = _truncate_raw([obs.model_dump(mode="json") for obs in result.observations])
    as_of = max(
        (datetime.combine(obs.date, datetime.min.time(), tzinfo=UTC) for obs in result.observations),
        default=None,
    )
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_fed_press(*, client: httpx.AsyncClient) -> TestPullPayload:
    items, _ = await fed_press_client.fetch_fed_press_releases(client=client)
    rows = _truncate_rows(
        [
            {
                "title": item.title,
                "kind": item.kind,
                "published_at": _iso(item.published_at),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    as_of = max((item.published_at for item in items), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_cme_fedwatch(*, client: httpx.AsyncClient) -> TestPullPayload:
    settings = get_settings()
    if settings.cme_fedwatch_base_url is None:
        raise SourceClientConfigError(setting_name="cme_fedwatch_base_url")
    meeting, _ = await cme_fedwatch_client.fetch_cme_fedwatch_probabilities(
        client=client,
        meeting_date=_today(),
        base_url=settings.cme_fedwatch_base_url,
    )
    rows = _truncate_rows(
        [
            {
                "meeting_date": _iso(meeting.meeting_date),
                "target_low_bps": prob.target_low_bps,
                "target_high_bps": prob.target_high_bps,
                "probability": prob.probability,
            }
            for prob in meeting.probabilities
        ]
    )
    raw = _truncate_raw(meeting.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=meeting.as_of)


async def fetch_kalshi_markets(*, client: httpx.AsyncClient) -> TestPullPayload:
    response, _ = await kalshi_client.fetch_kalshi_markets(client=client)
    rows = _truncate_rows(
        [
            {
                "ticker": market.ticker,
                "title": market.title,
                "status": market.status,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
            }
            for market in response.markets
        ]
    )
    raw = _truncate_raw([market.model_dump(mode="json") for market in response.markets])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_polymarket_events(*, client: httpx.AsyncClient) -> TestPullPayload:
    events, _ = await polymarket_client.fetch_polymarket_events(
        client=client, active=True
    )
    rows = _truncate_rows(
        [
            {
                "slug": event.slug,
                "title": event.title,
                "category": event.category,
                "active": event.active,
            }
            for event in events
        ]
    )
    raw = _truncate_raw([event.model_dump(mode="json") for event in events])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_polymarket_price_history(*, client: httpx.AsyncClient) -> TestPullPayload:
    markets, _ = await polymarket_client.fetch_polymarket_markets(
        client=client, limit=1, active=True
    )
    if not markets:
        raise ValueError("no polymarket markets available")
    history, _ = await polymarket_data_client.fetch_polymarket_price_history(
        client=client, market=markets[0].id, interval="1d"
    )
    rows = _truncate_rows(
        [
            {
                "timestamp_s": point.timestamp_s,
                "probability": point.probability,
            }
            for point in history.history
        ]
    )
    raw = _truncate_raw([point.model_dump(mode="json") for point in history.history])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_congress_bills(*, client: httpx.AsyncClient) -> TestPullPayload:
    response, _ = await congress_gov_client.fetch_congress_bills(
        client=client, limit=MAX_PREVIEW_ROWS
    )
    rows = _truncate_rows(
        [
            {
                "congress": bill.congress,
                "number": bill.number,
                "title": bill.title,
                "updateDate": _iso(bill.updateDate),
            }
            for bill in response.bills
        ]
    )
    raw = _truncate_raw([bill.model_dump(mode="json") for bill in response.bills])
    as_of = max(
        (bill.updateDate for bill in response.bills if bill.updateDate is not None),
        default=None,
    )
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


FetcherFn = Callable[..., Awaitable[TestPullPayload]]

TICKER_FETCHERS: dict[str, FetcherFn] = {
    "finnhub_insider_transactions": fetch_finnhub_insider_transactions,
    "finnhub_news": fetch_finnhub_news,
    "finnhub_peers": fetch_finnhub_peers,
    "finnhub_price_target": fetch_finnhub_price_target,
    "finnhub_profile": fetch_finnhub_profile,
    "finnhub_recommendation": fetch_finnhub_recommendation,
    "polygon_aggregates": fetch_polygon_aggregates,
    "sec_filings": fetch_sec_filings,
    "tiingo_news_items": fetch_tiingo_news_items,
    "gdelt": fetch_gdelt,
}

MACRO_FETCHERS: dict[str, FetcherFn] = {
    "fred_observations": fetch_fred_observations,
    "fed_press": fetch_fed_press,
    "cme_fedwatch": fetch_cme_fedwatch,
    "kalshi_markets": fetch_kalshi_markets,
    "polymarket_events": fetch_polymarket_events,
    "polymarket_price_history": fetch_polymarket_price_history,
    "congress_bills": fetch_congress_bills,
}

__all__ = [
    "DEFAULT_FRED_SERIES",
    "MACRO_FETCHERS",
    "MAX_PREVIEW_ROWS",
    "MAX_RAW_BYTES",
    "TICKER_FETCHERS",
    "FetcherFn",
    "TestPullPayload",
    "fetch_cme_fedwatch",
    "fetch_congress_bills",
    "fetch_fed_press",
    "fetch_finnhub_insider_transactions",
    "fetch_finnhub_news",
    "fetch_finnhub_peers",
    "fetch_finnhub_price_target",
    "fetch_finnhub_profile",
    "fetch_finnhub_recommendation",
    "fetch_fred_observations",
    "fetch_gdelt",
    "fetch_kalshi_markets",
    "fetch_polygon_aggregates",
    "fetch_polymarket_events",
    "fetch_polymarket_price_history",
    "fetch_sec_filings",
    "fetch_tiingo_news_items",
]
