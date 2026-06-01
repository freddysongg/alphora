from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransactionsResponse,
    FinnhubNewsItem,
    FinnhubRecommendation,
)
from app.services.source_clients.fred import FredSeriesObservations

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


__all__ = [
    "available_utc",
    "fred_observations_to_frame",
    "insider_events_to_frame",
    "news_events_to_frame",
    "recommendation_events_to_frame",
]
