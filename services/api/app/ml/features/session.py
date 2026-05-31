from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]

from app.services.market_clock import RTH_CLOSE_ET_MIN, RTH_OPEN_ET_MIN, to_et

_ET = ZoneInfo("America/New_York")


def build_session_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Session/time-of-day features aligned to `bars.index` (UTC DatetimeIndex)."""
    minutes_since_open: list[int] = []
    day_of_week: list[int] = []
    for ts in bars.index:
        clock = to_et(ts)
        minutes_since_open.append(clock.minutes - RTH_OPEN_ET_MIN)
        day_of_week.append(ts.astimezone(_ET).weekday())

    out = pd.DataFrame(index=bars.index)
    out["minutes_since_open"] = minutes_since_open
    out["day_of_week"] = day_of_week
    out["is_first_30min"] = [0 <= m <= 30 for m in minutes_since_open]
    last_30_start = (RTH_CLOSE_ET_MIN - RTH_OPEN_ET_MIN) - 30
    out["is_last_30min"] = [m >= last_30_start for m in minutes_since_open]
    return out


__all__ = ["build_session_features"]
