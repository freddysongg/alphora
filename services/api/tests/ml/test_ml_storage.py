from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from app.ml.storage import read_parquet, write_json, write_parquet


def test_write_then_read_roundtrips_index(tmp_path: Path) -> None:
    idx = pd.DatetimeIndex(
        ["2025-01-02T14:30:00Z", "2025-01-02T14:35:00Z"], tz="UTC", name="timestamp"
    )
    frame = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
    target = tmp_path / "sub" / "bars.parquet"

    write_parquet(frame, target)
    loaded = read_parquet(target)

    assert list(loaded.columns) == ["close"]
    assert loaded.index.tz is not None
    assert loaded.index.name == "timestamp"
    assert loaded["close"].tolist() == [1.0, 2.0]


def test_write_parquet_creates_parent_dirs(tmp_path: Path) -> None:
    frame = pd.DataFrame({"a": [1]})
    target = tmp_path / "deep" / "nested" / "x.parquet"
    write_parquet(frame, target)
    assert target.exists()


def test_write_json_writes_sorted_readable(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    write_json({"b": 1, "a": 2}, target)
    text = target.read_text()
    parsed = json.loads(text)
    assert parsed == {"a": 2, "b": 1}
    assert text.endswith("\n")
