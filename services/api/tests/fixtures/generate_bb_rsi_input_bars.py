"""Generate a deterministic 120-bar input series for the BB+RSI golden test.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_bb_rsi_input_bars.py

Rewrites `tests/fixtures/bb_rsi_input_bars.json` in place. The output is
committed; regenerate only when you intentionally want a new reference
series (and then re-run the .cjs generator).

Series design:
  - 120 bars at 1-minute intervals.
  - Start: 2026-06-15 13:30 UTC (= 09:30 ET, RTH open; BB+RSI doesn't
    use the session gate but we keep the timestamps RTH-aligned for
    visual consistency).
  - Wider sine wave (amplitude +/-3, wavelength ~30 bars) to push price
    through the Bollinger bands several times and pull RSI through
    both extremes.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BAR_COUNT = 120
_BASE_TS = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
_DRIFT_PER_MIN = 0.0
_AMP = 3.0
_WAVELEN_MIN = 30


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
    out_path = Path(__file__).parent / "bb_rsi_input_bars.json"
    out_path.write_text(json.dumps(bars, indent=2) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
