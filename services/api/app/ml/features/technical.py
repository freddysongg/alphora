from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.indicators import adx, atr, bollinger, ema, macd, rsi
from app.ml.config import FeatureConfig


def build_technical_features(bars: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Technical-indicator features aligned to `bars.index`, reusing app.indicators.

    All wrappers in app.indicators are causal and warmup-masked; this function
    only assembles and derives ratios. Warmup NaNs are dropped during assembly.
    """
    close = bars["close"].astype("float64")
    out = pd.DataFrame(index=bars.index)

    out["rsi"] = rsi(close, period=config.rsi_period)

    macd_line, macd_signal, macd_hist = macd(close)
    out["macd_line"] = macd_line
    out["macd_signal"] = macd_signal
    out["macd_hist"] = macd_hist

    out["adx"] = adx(bars, period=config.adx_period)
    out["atr"] = atr(bars, period=config.atr_period)

    _middle, upper, lower = bollinger(
        close, period=config.bollinger_period, mult=config.bollinger_mult
    )
    band_width = (upper - lower).replace(0.0, float("nan"))
    out["bb_pct"] = (close - lower) / band_width

    out["ema_fast_ratio"] = close / ema(close, period=config.ema_fast) - 1.0
    out["ema_slow_ratio"] = close / ema(close, period=config.ema_slow) - 1.0

    return out


__all__ = ["build_technical_features"]
