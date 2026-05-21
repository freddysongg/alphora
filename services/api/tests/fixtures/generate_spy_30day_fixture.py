"""Generate a deterministic 30-day, 1-minute SPY-shaped fixture.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_spy_30day_fixture.py

Rewrites `tests/fixtures/spy_30day_1min.json` (committed). Regenerate
only when you intentionally change the reference series.

Series design:
  - 30 weekdays starting 2026-04-01 (Wednesday).
  - 390 RTH 1-min bars per day (13:30-20:00 UTC, EDT-aligned).
  - Total: 30 * 390 = 11_700 bars.
  - Price model: random-walk seeded by bar index (deterministic), with
    intraday volatility tuned to produce multiple MACD crossovers and
    occasional ADX > 25 trend stretches.
  - Volume: 1000-5000, all strictly positive.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TRADING_DAYS = 30
_BARS_PER_DAY = 390  # 6.5 hours * 60 min
_BASE_PRICE = 500.0
_BASE_DATE = datetime(2026, 4, 1, 13, 30, tzinfo=UTC)


def _next_weekday(d: datetime) -> datetime:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _bar(price: float, ts: datetime) -> dict[str, float | int]:
    spread = 0.05
    return {
        "t": int(ts.timestamp() * 1000),
        "o": round(price, 4),
        "h": round(price + spread, 4),
        "l": round(price - spread, 4),
        "c": round(price, 4),
        "v": 1000.0 + 4000.0 * (0.5 + 0.5 * math.sin(ts.timestamp() / 600.0)),
    }


def _generate() -> list[dict[str, float | int]]:
    bars: list[dict[str, float | int]] = []
    price = _BASE_PRICE
    day = _BASE_DATE
    days_emitted = 0
    while days_emitted < _TRADING_DAYS:
        for i in range(_BARS_PER_DAY):
            ts = day + timedelta(minutes=i)
            phase = (days_emitted * _BARS_PER_DAY + i) / 30.0
            drift = 0.003 * math.sin(phase * 0.07)
            wave = 0.20 * math.sin(phase) + 0.12 * math.sin(phase * 0.37 + 1.1)
            price = max(1.0, price + drift + wave - 0.16 * math.sin(phase * 0.51))
            bars.append(_bar(price, ts))
        days_emitted += 1
        day = _next_weekday(day).replace(hour=13, minute=30, second=0, microsecond=0)
    return bars


def main() -> None:
    bars = _generate()
    out_path = Path(__file__).parent / "spy_30day_1min.json"
    out_path.write_text(json.dumps(bars) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
