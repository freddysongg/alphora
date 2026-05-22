"""Generate a deterministic 500-bar input series for the Confluence-Long golden test.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_confluence_long_input_bars.py

Rewrites `tests/fixtures/confluence_long_input_bars.json`. Series design:
  - 500 1-min bars starting 2026-06-15 13:30 UTC.
  - Bars 0-100: flat at 100 (lets the 5-min ADX warmup advance past the
    `adx_length * 2 + 2 = 30` gate before any signal fires).
  - Bars 100-140: slow drop 100 -> 80 (slope -0.5/bar) -- primes the MACD
    line slightly negative.
  - Bars 140-160: plateau at 80 (allows the MACD signal line to catch up
    before the sharp leg).
  - Bars 160-180: sharp drop 80 -> 50 (slope -1.5/bar) -- pushes MACD
    well below the -3 threshold.
  - Bars 180-230: recovery 50 -> 100 (slope +1.0/bar) -- triggers the
    MACD-crosses-signal-below-threshold event and the EMA(8) > EMA(21)
    crossover within the 12-bar lookback window.
  - Bars 230-500: gentle oscillation around 100 (carry / holding phase).
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BARS = 500
_BASE = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
_WARMUP_END = 100
_SLOW_DROP_END = 140
_PLATEAU_END = 160
_SHARP_DROP_END = 180
_RECOVERY_END = 230
_PLATEAU_PRICE = 80.0
_TROUGH_PRICE = 50.0
_LEVEL_PRICE = 100.0
_SLOW_DROP_SLOPE = (_LEVEL_PRICE - _PLATEAU_PRICE) / (_SLOW_DROP_END - _WARMUP_END)
_SHARP_DROP_SLOPE = (_PLATEAU_PRICE - _TROUGH_PRICE) / (_SHARP_DROP_END - _PLATEAU_END)
_RECOVERY_SLOPE = (_LEVEL_PRICE - _TROUGH_PRICE) / (_RECOVERY_END - _SHARP_DROP_END)


def _close(i: int) -> float:
    if i < _WARMUP_END:
        return _LEVEL_PRICE
    if i < _SLOW_DROP_END:
        return _LEVEL_PRICE - (i - _WARMUP_END) * _SLOW_DROP_SLOPE
    if i < _PLATEAU_END:
        return _PLATEAU_PRICE
    if i < _SHARP_DROP_END:
        return _PLATEAU_PRICE - (i - _PLATEAU_END) * _SHARP_DROP_SLOPE
    if i < _RECOVERY_END:
        return _TROUGH_PRICE + (i - _SHARP_DROP_END) * _RECOVERY_SLOPE
    return _LEVEL_PRICE + 0.3 * math.sin(i * 0.1)


def main() -> None:
    bars = []
    for i in range(_BARS):
        c = _close(i)
        ts = _BASE + timedelta(minutes=i)
        bars.append(
            {
                "t": int(ts.timestamp() * 1000),
                "o": round(c, 4),
                "h": round(c + 0.3, 4),
                "l": round(c - 0.3, 4),
                "c": round(c, 4),
                "v": 1000.0,
            }
        )
    out_path = Path(__file__).parent / "confluence_long_input_bars.json"
    out_path.write_text(json.dumps(bars) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
