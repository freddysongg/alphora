from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]

from app.services.market_clock import (
    MORNING_CUTOFF_ET_MIN,
    RTH_CLOSE_ET_MIN,
    RTH_OPEN_ET_MIN,
    et_day,
    et_minutes,
    is_us_market_open,
    to_et,
)

_NEW_YORK: ZoneInfo = ZoneInfo("America/New_York")


def _ny(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=_NEW_YORK)


def test_saturday_is_closed() -> None:
    saturday = _ny(2025, 2, 1, 12, 0)
    assert is_us_market_open(saturday) is False


def test_sunday_is_closed() -> None:
    sunday = _ny(2025, 2, 2, 12, 0)
    assert is_us_market_open(sunday) is False


def test_weekday_morning_before_open_is_closed() -> None:
    weekday = _ny(2025, 2, 3, 9, 0)
    assert is_us_market_open(weekday) is False


def test_weekday_exactly_at_open_is_open() -> None:
    weekday = _ny(2025, 2, 3, 9, 30)
    assert is_us_market_open(weekday) is True


def test_weekday_midday_is_open() -> None:
    weekday = _ny(2025, 2, 3, 12, 0)
    assert is_us_market_open(weekday) is True


def test_weekday_one_minute_before_close_is_open() -> None:
    weekday = _ny(2025, 2, 3, 15, 59)
    assert is_us_market_open(weekday) is True


def test_weekday_exactly_at_close_is_closed() -> None:
    weekday = _ny(2025, 2, 3, 16, 0)
    assert is_us_market_open(weekday) is False


def test_weekday_after_close_is_closed() -> None:
    weekday = _ny(2025, 2, 3, 18, 30)
    assert is_us_market_open(weekday) is False


def test_utc_input_is_converted_to_eastern() -> None:
    utc_open = datetime(2025, 2, 3, 14, 30, tzinfo=ZoneInfo("UTC"))
    assert is_us_market_open(utc_open) is True


def test_constants_match_source_bot_minute_of_day() -> None:
    assert RTH_OPEN_ET_MIN == 9 * 60 + 30
    assert RTH_CLOSE_ET_MIN == 16 * 60
    assert MORNING_CUTOFF_ET_MIN == 11 * 60 + 30


def test_to_et_summer_edt_offset_minus_4() -> None:
    ts = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    result = to_et(ts)
    assert result.day == "2026-06-15"
    assert result.minutes == 9 * 60 + 30


def test_to_et_winter_est_offset_minus_5() -> None:
    ts = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
    result = to_et(ts)
    assert result.day == "2026-01-15"
    assert result.minutes == 9 * 60 + 30


def test_to_et_handles_pandas_timestamp() -> None:
    ts = pd.Timestamp("2026-06-15 13:30:00", tz="UTC")
    result = to_et(ts)
    assert result.day == "2026-06-15"
    assert result.minutes == 9 * 60 + 30


def test_to_et_naive_datetime_treated_as_utc() -> None:
    ts = datetime(2026, 6, 15, 13, 30)
    result = to_et(ts)
    assert result.day == "2026-06-15"
    assert result.minutes == 9 * 60 + 30


def test_et_day_returns_iso_date_string() -> None:
    assert et_day(datetime(2026, 6, 15, 13, 30, tzinfo=UTC)) == "2026-06-15"


def test_et_minutes_returns_minute_of_day() -> None:
    assert et_minutes(datetime(2026, 6, 15, 13, 30, tzinfo=UTC)) == 9 * 60 + 30


def test_to_et_late_evening_utc_rolls_to_prior_et_day_in_winter() -> None:
    ts = datetime(2026, 1, 15, 2, 0, tzinfo=UTC)
    result = to_et(ts)
    assert result.day == "2026-01-14"
    assert result.minutes == 21 * 60


def test_is_us_market_open_still_works_after_extension() -> None:
    assert is_us_market_open(datetime(2026, 6, 15, 13, 30, tzinfo=UTC)) is True
    assert is_us_market_open(datetime(2026, 6, 15, 12, 0, tzinfo=UTC)) is False
