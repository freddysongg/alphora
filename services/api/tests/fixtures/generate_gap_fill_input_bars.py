"""Generate a deterministic 3-day RTH 1-min input series for the GapFill golden test.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_gap_fill_input_bars.py

Rewrites `tests/fixtures/gap_fill_input_bars.json`. Series design:
  - 3 trading days starting 2026-06-15 (Mon, EDT).
  - 390 RTH 1-min bars per day (13:30-20:00 UTC).
  - Day 1: flat at 100 (defines prior_close = 100 for day 2 lookups).
  - Day 2: opens at 108 (gap +8 over day-1 prior_close = 100), drifts
    down to 100 by minute 240 (fade short fires after the 15-min wait,
    gap fills mid-session, well before the 14:00 ET cutoff at min 270).
    Each bar's open is the prior bar's close so c < o on the down drift,
    which satisfies the source-bot quirk that 'todayOpen' resolves to
    the LATEST today bar's open, not the 9:30 RTH open.
  - Day 3: opens at 100, drifts up to 110 by minute 240. Because the
    source bot's priorClose walks back through ALL prior-day RTH bars
    overwriting each iteration, day 3's prior_close lands on the
    EARLIEST day-2 RTH bar (= 108), producing gap = 100 - 108 = -8.
    Fade long fires; gap fills when price reaches 108 (~minute 192).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TRADING_DAYS = 3
_BARS_PER_DAY = 390
_BASE_DATE = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)


def _next_weekday(d: datetime) -> datetime:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


_FILL_BAR = 240


def _day_price(day_idx: int, i: int) -> float:
    if day_idx == 0:
        return 100.0
    if day_idx == 1:
        base_open = 108.0
        target = 100.0
    else:
        base_open = 100.0
        target = 110.0
    if i <= 0:
        return base_open
    if i < _FILL_BAR:
        t = i / float(_FILL_BAR)
        return base_open + (target - base_open) * t
    return target


def _bar(o_price: float, c_price: float, ts: datetime) -> dict[str, float]:
    hi = max(o_price, c_price) + 0.5
    lo = min(o_price, c_price) - 0.5
    return {
        "t": int(ts.timestamp() * 1000),
        "o": round(o_price, 4),
        "h": round(hi, 4),
        "l": round(lo, 4),
        "c": round(c_price, 4),
        "v": 1000.0,
    }


def main() -> None:
    bars: list[dict[str, float]] = []
    day = _BASE_DATE
    for day_idx in range(_TRADING_DAYS):
        for i in range(_BARS_PER_DAY):
            ts = day + timedelta(minutes=i)
            if i == 0:
                o_price = _day_price(day_idx, 0)
                c_price = _day_price(day_idx, 0)
            else:
                o_price = _day_price(day_idx, i - 1)
                c_price = _day_price(day_idx, i)
            bars.append(_bar(o_price, c_price, ts))
        day = _next_weekday(day).replace(hour=13, minute=30, second=0, microsecond=0)
    out_path = Path(__file__).parent / "gap_fill_input_bars.json"
    out_path.write_text(json.dumps(bars) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
