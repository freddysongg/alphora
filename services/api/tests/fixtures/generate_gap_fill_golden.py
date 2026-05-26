"""Regenerate gap_fill_golden.json from our Python GapFillStrategy.

Replaces the prior Node-driven golden generator (which produced output
from a source-bot implementation with a known reference-price bug). The
Python port now uses semantically correct gap-fill references; this
generator captures its bar-by-bar output as the regression snapshot.

Run from `services/api/`:

    .venv/bin/python tests/fixtures/generate_gap_fill_golden.py
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from app.strategies.gap_fill import GapFillStrategy


def main() -> None:
    fixtures_dir = Path(__file__).parent
    raw = json.loads((fixtures_dir / "gap_fill_input_bars.json").read_text())
    timestamps = [datetime.fromtimestamp(int(b["t"]) / 1000.0, tz=UTC) for b in raw]
    bars = pd.DataFrame(
        {
            "open": [float(b["o"]) for b in raw],
            "high": [float(b["h"]) for b in raw],
            "low": [float(b["l"]) for b in raw],
            "close": [float(b["c"]) for b in raw],
            "volume": [float(b["v"]) for b in raw],
        },
        index=pd.DatetimeIndex(timestamps, tz="UTC"),
    )
    strategy = GapFillStrategy()
    current_pos = 0
    outputs: list[dict[str, object]] = []
    for i in range(len(raw)):
        primary = bars.iloc[: i + 1]
        result = strategy.evaluate(
            primary_bars=primary,
            secondary_bars={},
            current_position=current_pos,
            params={},
        )
        outputs.append(
            {
                "i": i,
                "t": int(raw[i]["t"]),
                "c": float(raw[i]["c"]),
                "current_pos_in": current_pos,
                "target": result.target,
                "meta": dict(result.meta),
            }
        )
        current_pos = result.target

    out_path = fixtures_dir / "gap_fill_golden.json"
    out_path.write_text(json.dumps(outputs, indent=2) + "\n")
    print(f"wrote {len(outputs)} reference rows to {out_path}")


if __name__ == "__main__":
    main()
