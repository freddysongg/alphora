from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.base import (
    Bars,
    Strategy,
    StrategyParams,
    StrategyResult,
    Timeframe,
    TrailSpec,
)


def test_bars_alias_is_pandas_dataframe() -> None:
    bars: Bars = pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []}
    )
    assert isinstance(bars, pd.DataFrame)


def test_strategy_params_alias_accepts_scalar_dict() -> None:
    params: StrategyParams = {"fast": 12, "slow": 26, "use_filter": True, "label": "default"}
    assert params["fast"] == 12
    assert params["use_filter"] is True
    assert params["label"] == "default"


def test_trail_spec_holds_atr_multiplier_and_period() -> None:
    spec = TrailSpec(atr_multiplier=1.5, atr_period=14)
    assert spec.atr_multiplier == 1.5
    assert spec.atr_period == 14


def test_strategy_result_target_must_be_in_minus_one_zero_one() -> None:
    flat = StrategyResult(target=0, meta={})
    long_ = StrategyResult(target=1, meta={"cross": "BULL"})
    short = StrategyResult(target=-1, meta={"cross": "BEAR"})
    assert flat.target == 0
    assert long_.target == 1
    assert short.target == -1


def test_strategy_result_optional_fields_default_to_none() -> None:
    r = StrategyResult(target=0, meta={})
    assert r.size_hint is None
    assert r.stop_pts is None
    assert r.target_pts is None
    assert r.trail is None


def test_strategy_protocol_attributes_documented() -> None:
    # Protocol attributes are part of the Protocol contract — verify the
    # class names exist (a real concrete strategy is verified in Task 8).
    assert Strategy.__name__ == "Strategy"
    assert Timeframe is not None
