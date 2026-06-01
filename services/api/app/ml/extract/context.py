from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig, PathConfig
from app.ml.extract.bars import month_windows
from app.ml.storage import write_parquet
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransactionsResponse,
    FinnhubNewsItem,
    FinnhubRecommendation,
    fetch_finnhub_company_news,
    fetch_finnhub_insider_transactions,
    fetch_finnhub_recommendation,
)
from app.services.source_clients.fred import (
    FredSeriesObservations,
    fetch_series_observations,
)

_ET = "America/New_York"
_UTC = "UTC"

_INSIDER_COLUMNS = ["available_ts", "change"]
_RECOMMENDATION_COLUMNS = ["available_ts", "net_score"]
_FRED_COLUMNS = ["available_ts", "value"]


def available_utc(day: date, lag_days: int) -> pd.Timestamp:
    """ET-midnight of ``day + lag_days`` expressed in UTC.

    A value dated ``day`` only becomes usable on bars at or after this instant,
    so with ``lag_days >= 1`` it can never appear on a bar during ``day`` itself
    (whose intraday publish time is unknown). This is the single point-in-time
    lag convention shared by insider filings, recommendations, and FRED.
    """
    return (pd.Timestamp(day, tz=_ET) + pd.Timedelta(days=lag_days)).tz_convert(_UTC)


def _to_utc(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(_UTC) if ts.tzinfo is None else ts.tz_convert(_UTC)


def _next_month_start(period: date) -> date:
    if period.month == 12:
        return date(period.year + 1, 1, 1)
    return date(period.year, period.month + 1, 1)


def insider_events_to_frame(
    response: FinnhubInsiderTransactionsResponse, config: ContextConfig
) -> pd.DataFrame:
    """Canonical insider-transaction events: signed share `change` at filing time."""
    rows = [
        {
            "available_ts": available_utc(txn.filing_date, config.insider_lag_days),
            "change": int(txn.change),
        }
        for txn in response.data
    ]
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "change": pd.Series([], dtype="int64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_INSIDER_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


def news_events_to_frame(items: list[FinnhubNewsItem]) -> pd.DataFrame:
    """Canonical news events: just the UTC publish timestamps (counts derived later)."""
    timestamps = [_to_utc(item.published_at) for item in items]
    series = pd.Series(timestamps, dtype="datetime64[ns, UTC]")
    frame = pd.DataFrame({"published_ts": series})
    return frame.sort_values("published_ts").reset_index(drop=True)


def recommendation_events_to_frame(
    items: list[FinnhubRecommendation], config: ContextConfig
) -> pd.DataFrame:
    """Canonical recommendation events: net bullishness, known from next month start."""
    rows: list[dict[str, object]] = []
    for rec in items:
        total = rec.strong_buy + rec.buy + rec.hold + rec.sell + rec.strong_sell
        net = (
            (rec.strong_buy + rec.buy - rec.sell - rec.strong_sell) / total
            if total > 0
            else 0.0
        )
        rows.append(
            {
                "available_ts": available_utc(
                    _next_month_start(rec.period), config.recommendation_lag_days
                ),
                "net_score": float(net),
            }
        )
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "net_score": pd.Series([], dtype="float64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_RECOMMENDATION_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


def fred_observations_to_frame(
    parsed: FredSeriesObservations, config: ContextConfig
) -> pd.DataFrame:
    """Canonical FRED events: numeric observations at observation_date + lag."""
    rows: list[dict[str, object]] = []
    for obs in parsed.observations:
        if obs.value is None:
            continue
        rows.append(
            {
                "available_ts": available_utc(obs.date, config.fred_lag_days),
                "value": float(obs.value),
            }
        )
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "value": pd.Series([], dtype="float64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_FRED_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


async def pull_insider(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> Path:
    """Fetch insider transactions for `ticker` and cache canonical events to parquet."""
    response, _ = await fetch_finnhub_insider_transactions(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    frame = insider_events_to_frame(response, config)
    path = paths.context_path("insider", ticker)
    write_parquet(frame, path)
    return path


async def pull_news(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    paths: PathConfig,
) -> Path:
    """Fetch company news in month windows and cache canonical events to parquet."""
    frames: list[pd.DataFrame] = []
    for window_start, window_end in month_windows(from_date, to_date):
        items, _ = await fetch_finnhub_company_news(
            client=client, symbol=ticker, from_date=window_start, to_date=window_end
        )
        frames.append(news_events_to_frame(items))
    combined = (
        pd.concat(frames, ignore_index=True) if frames else news_events_to_frame([])
    )
    combined = combined.sort_values("published_ts").reset_index(drop=True)
    path = paths.context_path("news", ticker)
    write_parquet(combined, path)
    return path


async def pull_recommendation(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    config: ContextConfig,
    paths: PathConfig,
) -> Path:
    """Fetch the analyst-recommendation trend and cache canonical events to parquet."""
    items, _ = await fetch_finnhub_recommendation(client=client, symbol=ticker)
    frame = recommendation_events_to_frame(items, config)
    path = paths.context_path("recommendation", ticker)
    write_parquet(frame, path)
    return path


async def pull_fred(
    *,
    client: httpx.AsyncClient,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> list[Path]:
    """Fetch each configured FRED series over a history-padded window, cache to parquet."""
    observation_start = from_date - timedelta(days=config.fred_history_days)
    written: list[Path] = []
    for series_id in config.fred_series:
        parsed, _ = await fetch_series_observations(
            client=client,
            series_id=series_id,
            observation_start=observation_start,
            observation_end=to_date,
        )
        frame = fred_observations_to_frame(parsed, config)
        path = paths.context_path("fred", series_id)
        write_parquet(frame, path)
        written.append(path)
    return written


async def pull_context_for_ticker(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> None:
    """Fetch and cache all per-ticker context sources (insider, news, recommendation)."""
    await pull_insider(
        client=client, ticker=ticker, from_date=from_date, to_date=to_date,
        config=config, paths=paths,
    )
    await pull_news(
        client=client, ticker=ticker, from_date=from_date, to_date=to_date, paths=paths
    )
    await pull_recommendation(
        client=client, ticker=ticker, config=config, paths=paths
    )


__all__ = [
    "available_utc",
    "fred_observations_to_frame",
    "insider_events_to_frame",
    "news_events_to_frame",
    "pull_context_for_ticker",
    "pull_fred",
    "pull_insider",
    "pull_news",
    "pull_recommendation",
    "recommendation_events_to_frame",
]
