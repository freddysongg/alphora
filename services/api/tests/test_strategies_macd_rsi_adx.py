from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.strategies.base import Strategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


def test_strategy_static_metadata_matches_spec() -> None:
    strat = MacdRsiAdxStrategy()
    assert strat.key == "macd_rsi_adx"
    assert strat.name == "MACD+RSI+ADX"
    assert strat.primary_timeframe == "1min"
    assert strat.secondary_timeframes == []
    assert strat.requires_rth is True


def test_strategy_satisfies_strategy_protocol() -> None:
    s: Strategy = MacdRsiAdxStrategy()
    assert s.key == "macd_rsi_adx"


def test_evaluate_raises_until_implemented() -> None:
    strat = MacdRsiAdxStrategy()
    bars = pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []}
    )
    with pytest.raises(NotImplementedError):
        strat.evaluate(primary_bars=bars, secondary_bars={}, current_position=0, params={})
