from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.brokers.base import Bar
from app.services.strategy_indicator_window import (
    INDICATOR_WINDOW_BARS,
    BoundedBarBuffer,
)


def _bar(i: int) -> Bar:
    return Bar(
        ticker="SPY",
        timeframe="1min",
        open=Decimal(str(100.0 + i * 0.1)),
        high=Decimal(str(100.5 + i * 0.1)),
        low=Decimal(str(99.5 + i * 0.1)),
        close=Decimal(str(100.0 + i * 0.1)),
        volume=Decimal("1000"),
        vwap=None,
        as_of=datetime(2026, 6, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=i),
    )


def test_default_window_size() -> None:
    assert INDICATOR_WINDOW_BARS == 250


def test_buffer_appends_and_keeps_order() -> None:
    buf = BoundedBarBuffer(max_size=10)
    for i in range(5):
        buf.append(_bar(i))
    frame = buf.to_frame()
    assert len(frame) == 5
    assert frame["close"].iloc[0] == 100.0
    assert frame["close"].iloc[4] == 100.4
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]


def test_buffer_drops_oldest_at_capacity() -> None:
    """Appending 5 bars to a capacity-3 buffer retains bars 2, 3, 4."""
    buf = BoundedBarBuffer(max_size=3)
    for i in range(5):
        buf.append(_bar(i))
    frame = buf.to_frame()
    assert len(frame) == 3
    assert frame["close"].iloc[0] == 100.2
    assert frame["close"].iloc[-1] == 100.4


def test_buffer_to_frame_has_utc_datetime_index() -> None:
    buf = BoundedBarBuffer(max_size=5)
    for i in range(3):
        buf.append(_bar(i))
    frame = buf.to_frame()
    assert frame.index.tz is not None
    assert str(frame.index.tz) in {"UTC", "datetime.timezone.utc"}


def test_buffer_to_frame_empty_returns_empty_frame_with_columns() -> None:
    buf = BoundedBarBuffer(max_size=5)
    frame = buf.to_frame()
    assert len(frame) == 0
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]


def test_buffer_default_size_constructor() -> None:
    buf = BoundedBarBuffer()
    assert buf.max_size == INDICATOR_WINDOW_BARS


def test_buffer_seed_from_existing_bars() -> None:
    """The runner seeds the buffer from a historical-bars query on startup
    so the first live bar has indicator warmup already done. Bars beyond
    capacity are dropped; bars 10..19 are retained when seeding 20 into
    a capacity-10 buffer."""
    historical = [_bar(i) for i in range(20)]
    buf = BoundedBarBuffer(max_size=10)
    buf.seed(historical)
    frame = buf.to_frame()
    assert len(frame) == 10
    assert frame["close"].iloc[0] == 101.0
    assert frame["close"].iloc[-1] == 101.9
