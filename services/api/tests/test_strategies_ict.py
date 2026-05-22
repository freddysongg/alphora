from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import Strategy
from app.strategies.ict import IctStrategy


def _bars_from_ohlc(
    ohlc: list[tuple[float, float, float, float]], *, base: datetime
) -> pd.DataFrame:
    idx = [base + timedelta(minutes=i) for i in range(len(ohlc))]
    return pd.DataFrame(
        {
            "open":   [o for o, _, _, _ in ohlc],
            "high":   [h for _, h, _, _ in ohlc],
            "low":    [low for _, _, low, _ in ohlc],
            "close":  [c for _, _, _, c in ohlc],
            "volume": [1000.0] * len(ohlc),
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


def test_strategy_static_metadata() -> None:
    s = IctStrategy()
    assert s.key == "ict"
    assert s.name == "ICT"
    assert s.primary_timeframe == "1min"
    assert s.secondary_timeframes == []
    assert s.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = IctStrategy()
    assert s.key == "ict"


def test_offhours_returns_flat() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 50,
        base=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "offhours"


def test_carry_position_through_rth_holding_phase() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 50,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=10, params={})
    assert r.target == 1
    assert r.meta.get("phase") == "holding"


def test_no_confluence_returns_flat_when_flat_and_no_setup() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 30,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") in {"no-confluence", "warmup"}


def test_warmup_when_below_threshold_bars() -> None:
    s = IctStrategy()
    bars = _bars_from_ohlc(
        [(100.0, 100.5, 99.5, 100.0)] * 5,
        base=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    r = s.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
    assert r.target == 0
    assert r.meta.get("phase") == "warmup"
