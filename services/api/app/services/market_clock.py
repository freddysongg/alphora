"""US market-session helpers in America/New_York time.

`is_us_market_open` is the original Phase 0 helper -- it answers "is RTH
open at this instant" for the polling-side code. Phase 3 adds the
lower-level building blocks the new strategies need: `to_et(ts)` returns
the bar's ET wallclock as `EtClock(day, minutes)`, and three RTH-relevant
minute-of-day constants so strategy gates read like the source bot.

The source bot's reference is `lib/time.js` (toET via Intl.DateTimeFormat
'America/New_York'); we use `zoneinfo.ZoneInfo("America/New_York")` which
handles DST identically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]

_NEW_YORK: ZoneInfo = ZoneInfo("America/New_York")
_MARKET_OPEN: time = time(hour=9, minute=30)
_MARKET_CLOSE: time = time(hour=16, minute=0)
_SATURDAY_WEEKDAY: int = 5

RTH_OPEN_ET_MIN: int = 9 * 60 + 30
RTH_CLOSE_ET_MIN: int = 16 * 60
MORNING_CUTOFF_ET_MIN: int = 11 * 60 + 30


@dataclass(frozen=True)
class EtClock:
    """ET wallclock of a single bar timestamp.

    `day` is an ISO-format `YYYY-MM-DD` string in America/New_York.
    `minutes` is the minute-of-day in ET (0..1439). Mirrors the source
    bot's `toET()` return shape in `lib/time.js`.
    """

    day: str
    minutes: int


def _to_aware_utc(ts: datetime | pd.Timestamp) -> datetime:
    if isinstance(ts, pd.Timestamp):
        py_ts = cast(datetime, ts.to_pydatetime())
    else:
        py_ts = ts
    if py_ts.tzinfo is None:
        py_ts = py_ts.replace(tzinfo=UTC)
    return py_ts


def to_et(ts: datetime | pd.Timestamp) -> EtClock:
    """Convert a UTC bar timestamp to an `EtClock` in America/New_York.

    Naive datetimes are treated as UTC (matches source bot -- ProjectX bar
    `t` values are UTC milliseconds with no tz info).
    """
    utc_ts = _to_aware_utc(ts)
    local = utc_ts.astimezone(_NEW_YORK)
    return EtClock(
        day=local.strftime("%Y-%m-%d"),
        minutes=local.hour * 60 + local.minute,
    )


def et_day(ts: datetime | pd.Timestamp) -> str:
    return to_et(ts).day


def et_minutes(ts: datetime | pd.Timestamp) -> int:
    return to_et(ts).minutes


def is_us_market_open(now: datetime | None = None) -> bool:
    """Return True when the US equities core session is open at `now`.

    Core session is Mon-Fri 09:30-16:00 America/New_York. The right edge
    (16:00) is exclusive. Market holidays are not handled in v1 -- early
    closes and full closures will be added in a follow-up calendar layer.
    """
    current = now if now is not None else datetime.now(UTC)
    local = current.astimezone(_NEW_YORK)
    if local.weekday() >= _SATURDAY_WEEKDAY:
        return False
    local_time = local.time()
    return _MARKET_OPEN <= local_time < _MARKET_CLOSE


__all__ = [
    "EtClock",
    "MORNING_CUTOFF_ET_MIN",
    "RTH_CLOSE_ET_MIN",
    "RTH_OPEN_ET_MIN",
    "et_day",
    "et_minutes",
    "is_us_market_open",
    "to_et",
]
