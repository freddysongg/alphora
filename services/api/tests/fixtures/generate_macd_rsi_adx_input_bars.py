"""Generate a deterministic OHLCV input series for the MACD+RSI+ADX
golden-output regression test.

Run from `services/api/`:

    python tests/fixtures/generate_macd_rsi_adx_input_bars.py

This rewrites `tests/fixtures/macd_rsi_adx_input_bars.json` in place.
The output is committed; regenerate only when you intentionally want a
new reference series (and then re-capture the golden output in the Node
script that consumes the same JSON).

Series design:
  - 120 bars at 1-minute intervals.
  - Start: 2026-06-15 13:00 UTC (= 09:00 ET, before RTH open).
  - End:   2026-06-15 14:59 UTC (= 10:59 ET, inside RTH).
  - Drift + sinusoid → multiple MACD crossovers + ADX bumps.
  - High/low straddle close by ±0.5 so ADX/ATR are well-defined.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BAR_COUNT = 120
_BASE_TS = datetime(2026, 6, 15, 13, 0, tzinfo=UTC)
_DRIFT_PER_MIN = 0.05
_AMP = 2.0
_WAVELEN_MIN = 25


def _bar(i: int) -> dict[str, float]:
    ts = _BASE_TS + timedelta(minutes=i)
    close = 100.0 + _DRIFT_PER_MIN * i + _AMP * math.sin(2 * math.pi * i / _WAVELEN_MIN)
    return {
        "t": int(ts.timestamp() * 1000),
        "o": round(close, 4),
        "h": round(close + 0.5, 4),
        "l": round(close - 0.5, 4),
        "c": round(close, 4),
        "v": 1000.0,
    }


def main() -> None:
    bars = [_bar(i) for i in range(_BAR_COUNT)]
    out_path = Path(__file__).parent / "macd_rsi_adx_input_bars.json"
    out_path.write_text(json.dumps(bars, indent=2) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
