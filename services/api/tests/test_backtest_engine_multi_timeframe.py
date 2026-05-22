from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from app.services.backtest_engine import simulate
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe


@dataclass
class _MultiTfRecordingStrategy:
    key: str = "test_multi_tf"
    name: str = "MultiTfTest"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = field(default_factory=lambda: ["5min"])
    requires_rth: bool = False
    seen_secondaries: list[dict[Timeframe, Bars]] = field(default_factory=list)

    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        self.seen_secondaries.append(
            {tf: frame.copy() for tf, frame in secondary_bars.items()}
        )
        return StrategyResult(target=0, meta={"phase": "noop"})


def _minute_bars(*, n: int) -> pd.DataFrame:
    start = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [start + timedelta(minutes=i) for i in range(n)]
    closes = [100.0 + i * 0.1 for i in range(n)]
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


def test_simulate_passes_secondary_bars_dict_keyed_by_timeframe() -> None:
    strategy = _MultiTfRecordingStrategy()
    bars = _minute_bars(n=12)
    simulate(bars=bars, strategy=strategy, params={})
    assert len(strategy.seen_secondaries) == 12
    for seen in strategy.seen_secondaries:
        assert list(seen.keys()) == ["5min"]


def test_simulate_secondary_view_grows_as_primary_advances() -> None:
    strategy = _MultiTfRecordingStrategy()
    bars = _minute_bars(n=12)
    simulate(bars=bars, strategy=strategy, params={})
    assert len(strategy.seen_secondaries[0]["5min"]) == 1
    assert len(strategy.seen_secondaries[4]["5min"]) == 1
    assert len(strategy.seen_secondaries[5]["5min"]) == 2
    assert len(strategy.seen_secondaries[11]["5min"]) == 3


def test_simulate_strategies_with_no_secondary_timeframes_get_empty_dict() -> None:
    from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy

    bars = _minute_bars(n=12)

    @dataclass
    class _NoSecondary:
        key: str = "no_secondary"
        name: str = "NoSec"
        primary_timeframe: Timeframe = "1min"
        secondary_timeframes: list[Timeframe] = field(default_factory=list)
        requires_rth: bool = False
        seen: list[dict[Timeframe, Bars]] = field(default_factory=list)

        def evaluate(
            self,
            primary_bars: Bars,
            secondary_bars: dict[Timeframe, Bars],
            current_position: int,
            params: StrategyParams,
        ) -> StrategyResult:
            self.seen.append(secondary_bars)
            return StrategyResult(target=0, meta={})

    strategy = _NoSecondary()
    simulate(bars=bars, strategy=strategy, params={})
    assert all(s == {} for s in strategy.seen)
    simulate(bars=bars, strategy=MacdRsiAdxStrategy(), params={})
