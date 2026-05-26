from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.services.timeframes import resample_bars_to_timeframe


def _minute_bars(*, start: datetime, n: int, start_price: float = 100.0) -> pd.DataFrame:
    idx = [start + timedelta(minutes=i) for i in range(n)]
    closes = [start_price + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.05 for c in closes],
            "low": [c - 0.05 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_resample_5min_groups_into_5_bar_buckets() -> None:
    start = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    primary = _minute_bars(start=start, n=10)
    secondary = resample_bars_to_timeframe(primary, "5min")
    assert len(secondary) == 2
    assert float(secondary.iloc[0]["open"]) == float(primary.iloc[0]["open"])
    assert float(secondary.iloc[0]["close"]) == float(primary.iloc[4]["close"])
    assert float(secondary.iloc[0]["high"]) == max(float(primary.iloc[j]["high"]) for j in range(5))
    assert float(secondary.iloc[0]["low"]) == min(float(primary.iloc[j]["low"]) for j in range(5))
    assert float(secondary.iloc[0]["volume"]) == sum(float(primary.iloc[j]["volume"]) for j in range(5))


def test_resample_5min_exposes_in_flight_bucket_as_last_row() -> None:
    start = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    primary = _minute_bars(start=start, n=6)
    secondary = resample_bars_to_timeframe(primary, "5min")
    assert len(secondary) == 2
    assert float(secondary.iloc[1]["open"]) == float(primary.iloc[5]["open"])
    assert float(secondary.iloc[1]["close"]) == float(primary.iloc[5]["close"])
    assert float(secondary.iloc[1]["volume"]) == float(primary.iloc[5]["volume"])


def test_resample_drops_empty_buckets() -> None:
    day1 = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    day2 = datetime(2026, 6, 16, 13, 30, tzinfo=UTC)
    idx = [day1, day1 + timedelta(minutes=1), day2]
    primary = pd.DataFrame(
        {
            "open":   [100.0, 100.1, 200.0],
            "high":   [100.5, 100.6, 200.5],
            "low":    [99.5,  99.6,  199.5],
            "close":  [100.0, 100.1, 200.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )
    secondary = resample_bars_to_timeframe(primary, "5min")
    assert len(secondary) == 2
    assert not secondary.isna().any().any()


def test_resample_empty_returns_empty() -> None:
    primary = pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []},
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    secondary = resample_bars_to_timeframe(primary, "5min")
    assert secondary.empty
    assert list(secondary.columns) == ["open", "high", "low", "close", "volume"]


def test_resample_unsupported_timeframe_raises() -> None:
    primary = _minute_bars(start=datetime(2026, 6, 15, 13, 30, tzinfo=UTC), n=5)
    with pytest.raises(ValueError, match="unsupported timeframe"):
        resample_bars_to_timeframe(primary, "3min")  # type: ignore[arg-type]
