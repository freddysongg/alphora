from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.market_clock import is_us_market_open

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
