from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig
from app.ml.extract.context import (
    available_utc,
    fred_observations_to_frame,
    insider_events_to_frame,
    news_events_to_frame,
    recommendation_events_to_frame,
)
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransaction,
    FinnhubInsiderTransactionsResponse,
    FinnhubNewsItem,
    FinnhubRecommendation,
)
from app.services.source_clients.fred import FredObservation, FredSeriesObservations


def test_available_utc_lags_into_next_et_midnight() -> None:
    ts = available_utc(date(2026, 5, 15), 1)
    assert str(ts.tz) == "UTC"
    assert ts == pd.Timestamp("2026-05-16 00:00", tz="America/New_York").tz_convert("UTC")


def test_insider_events_to_frame_lags_and_sorts() -> None:
    response = FinnhubInsiderTransactionsResponse(
        symbol="AAPL",
        data=[
            FinnhubInsiderTransaction(
                name="A", share=1000, change=-500, filingDate="2026-05-15",
                transactionDate="2026-05-13", transactionCode="S", transactionPrice=195.5,
            ),
            FinnhubInsiderTransaction(
                name="B", share=200, change=200, filingDate="2026-05-10",
                transactionDate="2026-05-08", transactionCode="P",
            ),
        ],
    )
    frame = insider_events_to_frame(response, ContextConfig())
    assert list(frame.columns) == ["available_ts", "change"]
    assert frame["available_ts"].is_monotonic_increasing
    assert frame["change"].tolist() == [200, -500]
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-05-11 00:00", tz="America/New_York").tz_convert("UTC")
    )


def test_news_events_to_frame_collects_utc_published_ts() -> None:
    items = [
        FinnhubNewsItem(
            id=1, category="company", headline="h", source="s",
            url="https://example.com/1", published_at="2026-05-15T13:00:00Z",
        ),
        FinnhubNewsItem(
            id=2, category="company", headline="h2", source="s",
            url="https://example.com/2", published_at="2026-05-14T20:00:00Z",
        ),
    ]
    frame = news_events_to_frame(items)
    assert list(frame.columns) == ["published_ts"]
    assert frame["published_ts"].is_monotonic_increasing
    assert str(frame["published_ts"].dt.tz) == "UTC"


def test_news_events_to_frame_empty_keeps_schema() -> None:
    frame = news_events_to_frame([])
    assert list(frame.columns) == ["published_ts"]
    assert frame.empty


def test_recommendation_events_to_frame_next_month_and_net_score() -> None:
    items = [
        FinnhubRecommendation(
            symbol="AAPL", period="2026-05-01", buy=20, hold=5, sell=2,
            strongBuy=10, strongSell=1,
        )
    ]
    frame = recommendation_events_to_frame(items, ContextConfig())
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-06-01 00:00", tz="America/New_York").tz_convert("UTC")
    )
    assert abs(frame["net_score"].iloc[0] - (10 + 20 - 2 - 1) / 38) < 1e-9


def test_fred_observations_to_frame_skips_missing_and_lags() -> None:
    parsed = FredSeriesObservations(
        series_id="DGS10",
        observation_start="2026-05-01",
        observation_end="2026-05-05",
        count=3,
        observations=[
            FredObservation(date="2026-05-01", value="4.25",
                            realtime_start="2026-05-02", realtime_end="2026-12-31"),
            FredObservation(date="2026-05-02", value=".",
                            realtime_start="2026-05-03", realtime_end="2026-12-31"),
            FredObservation(date="2026-05-05", value="4.30",
                            realtime_start="2026-05-06", realtime_end="2026-12-31"),
        ],
    )
    frame = fred_observations_to_frame(parsed, ContextConfig())
    assert frame["value"].tolist() == [4.25, 4.30]
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-05-02 00:00", tz="America/New_York").tz_convert("UTC")
    )
