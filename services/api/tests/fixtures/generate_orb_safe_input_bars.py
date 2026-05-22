"""Generate a deterministic 2-day RTH 1-min input series for the ORB-safe golden test.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_orb_safe_input_bars.py

Rewrites `tests/fixtures/orb_safe_input_bars.json`. Series design:
  - 2 trading days starting 2026-06-15 (Monday, EDT).
  - 390 RTH 1-min bars per day (13:30-20:00 UTC).
  - Day 1: flat OR (09:30-10:00 ET); upward drift after, exercising the
    long-breakout-above-VWAP path.
  - Day 2: flat OR; downward drift after, exercising the
    short-breakout path. A short late-day spike (~15:25 ET) exercises
    the EOD flatten gate.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TRADING_DAYS = 2
_BARS_PER_DAY = 390
_BASE_PRICE = 100.0
_BASE_DATE = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)


def _next_weekday(d: datetime) -> datetime:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _day_path(day_idx: int, i: int) -> float:
    if day_idx == 0:
        if i < 30:
            return 100.0 + 0.05 * math.sin(i)
        return 100.0 + (i - 30) * 0.05
    if day_idx == 1:
        if i < 30:
            return 100.0 + 0.05 * math.sin(i)
        if 350 <= i <= 355:
            return 100.0 - (350 - 30) * 0.05 + 2.0
        return 100.0 - (i - 30) * 0.05
    return 100.0


def _bar(price: float, ts: datetime) -> dict[str, float]:
    return {
        "t": int(ts.timestamp() * 1000),
        "o": round(price, 4),
        "h": round(price + 0.5, 4),
        "l": round(price - 0.5, 4),
        "c": round(price, 4),
        "v": 1000.0,
    }


def main() -> None:
    bars: list[dict[str, float]] = []
    day = _BASE_DATE
    for day_idx in range(_TRADING_DAYS):
        for i in range(_BARS_PER_DAY):
            ts = day + timedelta(minutes=i)
            bars.append(_bar(_day_path(day_idx, i), ts))
        day = _next_weekday(day).replace(hour=13, minute=30, second=0, microsecond=0)
    out_path = Path(__file__).parent / "orb_safe_input_bars.json"
    out_path.write_text(json.dumps(bars) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
