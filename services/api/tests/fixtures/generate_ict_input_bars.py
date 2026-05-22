"""Generate a deterministic 1-day RTH 1-min input series for the ICT golden test.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_ict_input_bars.py

Rewrites `tests/fixtures/ict_input_bars.json`. The shape includes a
brief rally that creates a swing high, a wicking move that sweeps it,
a sharp pullback that leaves a bearish FVG, and a small bounce into
that FVG zone (potential bear-ICT entry).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BARS = 390
_BASE = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)


def _path(i: int) -> tuple[float, float, float, float]:
    if i < 60:
        return (100.0, 100.5, 99.5, 100.0)
    if 60 <= i <= 100:
        c = 100.0 + (i - 60) * 0.05
        return (c, c + 0.3, c - 0.3, c)
    if 101 <= i <= 110:
        return (102.0, 102.5, 101.7, 102.0)
    if i == 111:
        return (102.0, 103.0, 101.5, 101.6)
    if 112 <= i <= 114:
        c = 101.6 - (i - 111) * 0.7
        return (c, c + 0.1, c - 0.1, c)
    if 115 <= i <= 118:
        c = 99.5 + (i - 115) * 0.2
        return (c, c + 0.1, c - 0.1, c)
    return (100.0, 100.5, 99.5, 100.0)


def main() -> None:
    bars = []
    for i in range(_BARS):
        o, h, low, c = _path(i)
        ts = _BASE + timedelta(minutes=i)
        bars.append(
            {
                "t": int(ts.timestamp() * 1000),
                "o": round(o, 4),
                "h": round(h, 4),
                "l": round(low, 4),
                "c": round(c, 4),
                "v": 1000.0,
            }
        )
    out_path = Path(__file__).parent / "ict_input_bars.json"
    out_path.write_text(json.dumps(bars) + "\n")
    print(f"wrote {len(bars)} bars to {out_path}")


if __name__ == "__main__":
    main()
