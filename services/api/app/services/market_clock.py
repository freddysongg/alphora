from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

_NEW_YORK: ZoneInfo = ZoneInfo("America/New_York")
_MARKET_OPEN: time = time(hour=9, minute=30)
_MARKET_CLOSE: time = time(hour=16, minute=0)
_SATURDAY_WEEKDAY: int = 5


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


__all__ = ["is_us_market_open"]
