from __future__ import annotations

import calendar
from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.services.market_clock import RTH_CLOSE_ET_MIN, RTH_OPEN_ET_MIN, to_et
from app.services.source_clients.polygon import PolygonAggregatesResponse

_COLUMNS = ["open", "high", "low", "close", "volume"]


def month_windows(from_date: date, to_date: date) -> list[tuple[date, date]]:
    """Split an inclusive [from_date, to_date] range into per-calendar-month windows.

    Keeps each Polygon aggregates request small enough to stay under the
    default 5000-row response cap for 5-minute bars (a month of extended-hours
    5-minute bars is well under that).
    """
    if from_date > to_date:
        raise ValueError("from_date must be <= to_date")
    windows: list[tuple[date, date]] = []
    cursor = from_date
    while cursor <= to_date:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        window_end = min(month_end, to_date)
        windows.append((cursor, window_end))
        if window_end.month == 12:
            cursor = date(window_end.year + 1, 1, 1)
        else:
            cursor = date(window_end.year, window_end.month + 1, 1)
    return windows


def bars_response_to_frame(response: PolygonAggregatesResponse) -> pd.DataFrame:
    """Convert a parsed Polygon aggregates response into a sorted OHLCV frame."""
    rows: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for bar in response.results:
        rows.append(
            {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
        timestamps.append(pd.Timestamp(bar.timestamp_ms, unit="ms", tz="UTC"))
    if not rows:
        return pd.DataFrame(
            {col: pd.Series(dtype="float64") for col in _COLUMNS},
            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"),
        )
    frame = pd.DataFrame(
        rows, index=pd.DatetimeIndex(timestamps, tz="UTC", name="timestamp")
    )
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[_COLUMNS]


def tag_rth(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `frame` with a boolean `is_rth` column (09:30-16:00 ET)."""
    flags = [
        RTH_OPEN_ET_MIN <= to_et(ts).minutes < RTH_CLOSE_ET_MIN for ts in frame.index
    ]
    out = frame.copy()
    out["is_rth"] = flags
    return out


__all__ = ["bars_response_to_frame", "month_windows", "tag_rth"]
