from __future__ import annotations

from datetime import date

import httpx
import pandas as pd  # type: ignore[import-untyped]
import respx

from app.ml.extract.bars import (
    bars_response_to_frame,
    fetch_bars_for_ticker,
    month_windows,
    tag_rth,
)
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)


def test_month_windows_splits_inclusive_range() -> None:
    windows = month_windows(date(2025, 1, 15), date(2025, 3, 10))
    assert windows[0] == (date(2025, 1, 15), date(2025, 1, 31))
    assert windows[1] == (date(2025, 2, 1), date(2025, 2, 28))
    assert windows[-1] == (date(2025, 3, 1), date(2025, 3, 10))


def test_month_windows_single_month() -> None:
    assert month_windows(date(2025, 5, 1), date(2025, 5, 20)) == [
        (date(2025, 5, 1), date(2025, 5, 20))
    ]


def test_bars_response_to_frame_sorts_and_renames() -> None:
    response = PolygonAggregatesResponse(
        ticker="AAPL",
        queryCount=2,
        resultsCount=2,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(o=2.0, c=2.5, h=2.6, l=1.9, v=200.0, t=1700000300000),
            PolygonAggregateBar(o=1.0, c=1.5, h=1.6, l=0.9, v=100.0, t=1700000000000),
        ],
    )
    frame = bars_response_to_frame(response)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.is_monotonic_increasing
    assert frame.index.tz is not None
    assert frame["close"].tolist() == [1.5, 2.5]


def test_tag_rth_flags_only_regular_hours() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-02T13:00:00Z",  # 08:00 ET pre-market
            "2025-01-02T14:30:00Z",  # 09:30 ET open
            "2025-01-02T20:55:00Z",  # 15:55 ET
            "2025-01-02T21:00:00Z",  # 16:00 ET close (exclusive)
        ],
        tz="UTC",
    )
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    tagged = tag_rth(frame)
    assert tagged["is_rth"].tolist() == [False, True, True, False]


@respx.mock
async def test_fetch_bars_for_ticker_concatenates_windows() -> None:
    def _payload(ts_ms: int, close: float) -> dict[str, object]:
        return {
            "ticker": "AAPL",
            "queryCount": 1,
            "resultsCount": 1,
            "adjusted": True,
            "status": "OK",
            "results": [{"o": 1.0, "c": close, "h": 2.0, "l": 0.5, "v": 10.0, "t": ts_ms}],
        }

    respx.get(url__regex=r".*/range/5/minute/2025-01-01/2025-01-31.*").mock(
        return_value=httpx.Response(200, json=_payload(1735830000000, 10.0))
    )
    respx.get(url__regex=r".*/range/5/minute/2025-02-01/2025-02-15.*").mock(
        return_value=httpx.Response(200, json=_payload(1738500000000, 20.0))
    )

    async with httpx.AsyncClient() as client:
        frame = await fetch_bars_for_ticker(
            client=client,
            ticker="AAPL",
            from_date=date(2025, 1, 1),
            to_date=date(2025, 2, 15),
        )

    assert len(frame) == 2
    assert frame.index.is_monotonic_increasing
    assert "is_rth" in frame.columns
    assert frame["close"].tolist() == [10.0, 20.0]
