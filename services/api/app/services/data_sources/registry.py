"""In-code source registry. The single source of truth for which ingestion
handlers map to which provider, label, scope, default lookback, API-key
setting field, and preview shape.

There is no DB table for the registry itself; persisted operator settings
live in `data_source_settings`, keyed by `entry.key`.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from app.schemas.data_sources import DataSourceScope


@dataclass(frozen=True)
class DataSourceEntry:
    key: str
    provider: str
    label: str
    caption: str
    scope: DataSourceScope
    default_lookback_days: int | None
    api_key_env: str | None
    preview_columns: tuple[str, ...]


DATA_SOURCE_REGISTRY: tuple[DataSourceEntry, ...] = (
    DataSourceEntry(
        key="finnhub_insider_transactions",
        provider="finnhub",
        label="Finnhub Insider Transactions",
        caption="Form 4 insider buys/sells for the symbol.",
        scope="ticker",
        default_lookback_days=90,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "name",
            "share",
            "change",
            "transaction_date",
            "transaction_code",
            "transaction_price",
        ),
    ),
    DataSourceEntry(
        key="finnhub_news",
        provider="finnhub",
        label="Finnhub Company News",
        caption="Recent news headlines for the symbol.",
        scope="ticker",
        default_lookback_days=30,
        api_key_env="finnhub_api_key",
        preview_columns=("headline", "source", "published_at"),
    ),
    DataSourceEntry(
        key="finnhub_peers",
        provider="finnhub",
        label="Finnhub Peers",
        caption="Peer ticker list derived by Finnhub.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=("peer",),
    ),
    DataSourceEntry(
        key="finnhub_price_target",
        provider="finnhub",
        label="Finnhub Price Target",
        caption="Aggregate analyst price target.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "target_low",
            "target_mean",
            "target_median",
            "target_high",
            "number_of_analysts",
            "last_updated",
        ),
    ),
    DataSourceEntry(
        key="finnhub_profile",
        provider="finnhub",
        label="Finnhub Profile",
        caption="Company profile metadata.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "name",
            "exchange",
            "finnhub_industry",
            "market_capitalization",
            "share_outstanding",
        ),
    ),
    DataSourceEntry(
        key="finnhub_recommendation",
        provider="finnhub",
        label="Finnhub Recommendation",
        caption="Analyst recommendation distribution.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=("period", "strong_buy", "buy", "hold", "sell", "strong_sell"),
    ),
    DataSourceEntry(
        key="polygon_aggregates",
        provider="polygon",
        label="Polygon Daily Aggregates",
        caption="OHLCV bars for the symbol.",
        scope="ticker",
        default_lookback_days=90,
        api_key_env="polygon_api_key",
        preview_columns=("timestamp_ms", "open", "high", "low", "close", "volume"),
    ),
    DataSourceEntry(
        key="sec_filings",
        provider="sec_edgar",
        label="SEC Recent Filings",
        caption="Most recent filings from EDGAR for the symbol's CIK.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=("form", "filing_date", "accession_number", "primary_document"),
    ),
    DataSourceEntry(
        key="tiingo_news_items",
        provider="tiingo",
        label="Tiingo News",
        caption="Headlines tagged for the symbol.",
        scope="ticker",
        default_lookback_days=30,
        api_key_env="tiingo_api_key",
        preview_columns=("title", "source", "publishedDate"),
    ),
    DataSourceEntry(
        key="gdelt",
        provider="gdelt",
        label="GDELT Articles",
        caption="Open news articles mentioning the symbol.",
        scope="ticker",
        default_lookback_days=7,
        api_key_env=None,
        preview_columns=("title", "domain", "seendate"),
    ),
    DataSourceEntry(
        key="fred_observations",
        provider="fred",
        label="FRED Series Observations",
        caption="Macro time series from St. Louis Fed (GDP by default).",
        scope="macro",
        default_lookback_days=None,
        api_key_env="fred_api_key",
        preview_columns=("date", "value"),
    ),
    DataSourceEntry(
        key="fed_press",
        provider="fed_press",
        label="Fed Press Releases & Speeches",
        caption="Recent FOMC press releases.",
        scope="macro",
        default_lookback_days=30,
        api_key_env=None,
        preview_columns=("title", "kind", "published_at"),
    ),
    DataSourceEntry(
        key="cme_fedwatch",
        provider="cme_fedwatch",
        label="CME FedWatch Probabilities",
        caption="Implied probabilities for the next FOMC.",
        scope="macro",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=("meeting_date", "target_low_bps", "target_high_bps", "probability"),
    ),
    DataSourceEntry(
        key="kalshi_markets",
        provider="kalshi",
        label="Kalshi Markets",
        caption="Live event markets.",
        scope="macro",
        default_lookback_days=None,
        api_key_env="kalshi_api_key",
        preview_columns=("ticker", "title", "status", "yes_bid", "yes_ask"),
    ),
    DataSourceEntry(
        key="polymarket_events",
        provider="polymarket",
        label="Polymarket Events",
        caption="Live event markets.",
        scope="macro",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=("slug", "title", "category", "active"),
    ),
    DataSourceEntry(
        key="polymarket_price_history",
        provider="polymarket",
        label="Polymarket Price History",
        caption="Historical prices for a single market.",
        scope="macro",
        default_lookback_days=30,
        api_key_env=None,
        preview_columns=("timestamp_s", "probability"),
    ),
    DataSourceEntry(
        key="congress_bills",
        provider="congress_gov",
        label="Congress Bills",
        caption="Recent bills introduced in Congress.",
        scope="macro",
        default_lookback_days=30,
        api_key_env="congress_api_key",
        preview_columns=("congress", "number", "title", "updateDate"),
    ),
)

_BY_KEY: dict[str, DataSourceEntry] = {entry.key: entry for entry in DATA_SOURCE_REGISTRY}


def get_entry(key: str) -> DataSourceEntry | None:
    return _BY_KEY.get(key)


def iter_entries() -> Iterator[DataSourceEntry]:
    return iter(DATA_SOURCE_REGISTRY)


__all__ = [
    "DATA_SOURCE_REGISTRY",
    "DataSourceEntry",
    "get_entry",
    "iter_entries",
]
