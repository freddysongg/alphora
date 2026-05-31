# 5-min ETL Core Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, leakage-free ETL that turns Polygon 5-minute bars for a curated liquid universe into a labeled (triple-barrier) feature dataset in parquet, ready for XGBoost training.

**Architecture:** New `services/api/app/ml/` subpackage. Reuses the existing Polygon client, `app.indicators`, and `app.services.market_clock`. Writes parquet under `services/api/data/ml/` — no Postgres writes. Pure transform functions are unit-tested with synthetic data; the one network stage is tested with `respx`. A `typer` CLI chains the stages.

**Tech Stack:** Python 3.12, pandas, pyarrow, pandas-ta (via `app.indicators`), httpx, typer, pytest + pytest-asyncio + respx. mypy `strict`, ruff.

**Scope note:** This plan is Plan A of two. The point-in-time **context layer** (insider/news/recommendation/FRED as-of joins, spec §5.3/§6) is **Plan B**, authored next, and layers onto this plan's `assemble.py` output. This plan delivers a complete, trainable dataset from the price spine alone.

**Spec:** `docs/superpowers/specs/2026-05-31-5min-etl-feature-pipeline-design.md`

---

## File structure

```
services/api/app/ml/
  __init__.py
  config.py            # frozen dataclasses: barrier, feature, path, top-level EtlConfig
  universe.py          # curated liquid universe constant + resolve_universe()
  storage.py           # parquet IO + path conventions
  extract/
    __init__.py
    bars.py            # Polygon 5-min bulk loader: month-window split, response->df, RTH tag, fetch loop
  features/
    __init__.py
    price.py           # log-returns, ranges, gaps, rel-volume, realized vol, vwap distance
    technical.py       # wraps app.indicators -> rsi/macd/adx/atr/%B/ema ratios
    session.py         # minutes-since-open, time bucket, day-of-week, first/last-30min flags
    normalize.py       # causal per-ticker rolling z-score
  labels/
    __init__.py
    triple_barrier.py  # ATR-scaled, session-aware triple-barrier labeler
  assemble.py          # per-ticker build + concat + drop warmup/tail + manifest + feature_spec
  cli.py               # typer app: pull-bars, build-dataset, run

services/api/tests/ml/
  __init__.py
  test_ml_config.py
  test_ml_universe.py
  test_ml_storage.py
  test_ml_extract_bars.py
  test_ml_features_price.py
  test_ml_features_technical.py
  test_ml_features_session.py
  test_ml_features_normalize.py
  test_ml_labels_triple_barrier.py
  test_ml_assemble.py
  test_ml_cli.py
  test_ml_integration.py
```

**Conventions to match (verified in repo):**
- All modules start with `from __future__ import annotations`.
- Tests: `pytest`, `pytest-asyncio` (`asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed but harmless), `respx` for HTTP, `tmp_path` for filesystem.
- Pure dataclasses are `@dataclass(frozen=True)`.
- mypy `strict`: explicit return types everywhere, no untyped defs, `import type`-equivalent care.
- pandas import line used in repo: `import pandas as pd  # type: ignore[import-untyped]`.

---

## Task 0: Scaffolding, dependency, gitignore

**Files:**
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/.gitignore`
- Create: `services/api/app/ml/__init__.py`
- Create: `services/api/app/ml/extract/__init__.py`
- Create: `services/api/app/ml/features/__init__.py`
- Create: `services/api/app/ml/labels/__init__.py`
- Create: `services/api/tests/ml/__init__.py`

- [ ] **Step 1: Add `ml` optional-dependency extra**

In `services/api/pyproject.toml`, after the existing `[project.optional-dependencies] dev = [...]` block, add:

```toml
ml = [
  "pyarrow>=17.0.0",
]
```

- [ ] **Step 2: Register the ETL CLI script**

In `services/api/pyproject.toml`, under `[project.scripts]`, add a line:

```toml
alphora-etl = "app.ml.cli:app"
```

- [ ] **Step 3: Ignore generated parquet**

Append to `services/api/.gitignore`:

```
data/ml/
```

- [ ] **Step 4: Create empty package markers**

Each of these files contains exactly:

```python
from __future__ import annotations
```

Create: `app/ml/__init__.py`, `app/ml/extract/__init__.py`, `app/ml/features/__init__.py`, `app/ml/labels/__init__.py`, `tests/ml/__init__.py`.

- [ ] **Step 5: Install the extra and verify import**

Run: `cd services/api && uv sync --extra ml --extra dev`
Then: `uv run python -c "import pyarrow, app.ml; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add services/api/pyproject.toml services/api/uv.lock services/api/.gitignore services/api/app/ml services/api/tests/ml
git commit -m "add: ml subpackage scaffold, pyarrow extra, etl cli script"
```

---

## Task 1: Config dataclasses

**Files:**
- Create: `services/api/app/ml/config.py`
- Test: `services/api/tests/ml/test_ml_config.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.ml.config import BarrierConfig, EtlConfig, FeatureConfig, PathConfig


def test_barrier_config_defaults() -> None:
    cfg = BarrierConfig()
    assert cfg.pt_mult == 2.0
    assert cfg.sl_mult == 1.0
    assert cfg.horizon_bars == 12
    assert cfg.atr_period == 14
    assert cfg.ambiguous_bar_resolution == "lower_first"


def test_feature_config_defaults() -> None:
    cfg = FeatureConfig()
    assert cfg.return_windows == (1, 3, 6, 12)
    assert cfg.normalize_window == 100
    assert cfg.rsi_period == 14


def test_paths_are_rooted_under_data_ml(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    assert paths.raw_bars_dir == tmp_path / "raw_bars" / "5min"
    assert paths.dataset_dir("run1") == tmp_path / "datasets" / "run1"


def test_etl_config_composes() -> None:
    cfg = EtlConfig(
        tickers=("AAPL", "SPY"),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
    )
    assert cfg.tickers == ("AAPL", "SPY")
    assert cfg.barrier.pt_mult == 2.0
    assert cfg.rth_only is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ml.config'`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

AmbiguousResolution = Literal["lower_first", "upper_first"]

_DEFAULT_ROOT = Path("data/ml")


@dataclass(frozen=True)
class BarrierConfig:
    pt_mult: float = 2.0
    sl_mult: float = 1.0
    horizon_bars: int = 12
    atr_period: int = 14
    ambiguous_bar_resolution: AmbiguousResolution = "lower_first"


@dataclass(frozen=True)
class FeatureConfig:
    return_windows: tuple[int, ...] = (1, 3, 6, 12)
    rsi_period: int = 14
    adx_period: int = 14
    atr_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 20
    bollinger_period: int = 20
    bollinger_mult: float = 2.0
    realized_vol_window: int = 12
    relative_volume_window: int = 20
    normalize_window: int = 100
    normalize_min_periods: int = 30


@dataclass(frozen=True)
class PathConfig:
    root: Path = _DEFAULT_ROOT

    @property
    def raw_bars_dir(self) -> Path:
        return self.root / "raw_bars" / "5min"

    def raw_bars_path(self, ticker: str) -> Path:
        return self.raw_bars_dir / f"{ticker}.parquet"

    @property
    def datasets_root(self) -> Path:
        return self.root / "datasets"

    def dataset_dir(self, run_id: str) -> Path:
        return self.datasets_root / run_id


@dataclass(frozen=True)
class EtlConfig:
    tickers: tuple[str, ...]
    from_date: date
    to_date: date
    rth_only: bool = True
    barrier: BarrierConfig = field(default_factory=BarrierConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    paths: PathConfig = field(default_factory=PathConfig)


__all__ = [
    "AmbiguousResolution",
    "BarrierConfig",
    "EtlConfig",
    "FeatureConfig",
    "PathConfig",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/config.py services/api/tests/ml/test_ml_config.py
git commit -m "add: ml etl config dataclasses"
```

---

## Task 2: Storage (parquet IO)

**Files:**
- Create: `services/api/app/ml/storage.py`
- Test: `services/api/tests/ml/test_ml_storage.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_storage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, engine="pyarrow", index=True)


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


__all__ = ["read_parquet", "write_json", "write_parquet"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_storage.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/storage.py services/api/tests/ml/test_ml_storage.py
git commit -m "add: ml parquet and json storage helpers"
```

---

## Task 3: Universe resolution

**Files:**
- Create: `services/api/app/ml/universe.py`
- Test: `services/api/tests/ml/test_ml_universe.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from app.ml.universe import CURATED_UNIVERSE, resolve_universe


def test_curated_universe_is_nonempty_unique_upper() -> None:
    assert len(CURATED_UNIVERSE) >= 50
    assert len(set(CURATED_UNIVERSE)) == len(CURATED_UNIVERSE)
    assert all(t == t.upper() for t in CURATED_UNIVERSE)
    assert "SPY" in CURATED_UNIVERSE
    assert "AAPL" in CURATED_UNIVERSE


def test_resolve_universe_default_returns_curated_sorted() -> None:
    resolved = resolve_universe()
    assert resolved == tuple(sorted(CURATED_UNIVERSE))


def test_resolve_universe_explicit_override_normalizes() -> None:
    resolved = resolve_universe(("msft", "aapl", "aapl"))
    assert resolved == ("AAPL", "MSFT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_universe.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

from collections.abc import Iterable

CURATED_UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    "XLI", "XLU", "XLB", "XLRE", "XLC", "VTI", "VOO", "GLD", "TLT", "HYG",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK.B", "JPM",
    "V", "MA", "UNH", "HD", "PG", "JNJ", "COST", "WMT", "BAC", "KO",
    "PEP", "ADBE", "CRM", "NFLX", "AMD", "INTC", "CSCO", "ORCL", "QCOM", "TXN",
    "DIS", "NKE", "MCD", "ABT", "TMO", "LIN", "ACN", "DHR", "WFC", "GS",
    "MS", "C", "AXP", "CAT", "BA", "GE", "HON", "UPS", "LMT", "RTX",
    "PFE", "MRK", "ABBV", "LLY", "BMY", "CVX", "XOM", "COP", "SLB", "PLTR",
)


def resolve_universe(tickers: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return a deterministic, de-duplicated, upper-cased, sorted ticker tuple.

    Passing `None` resolves the curated liquid large-cap + major-ETF list.
    Passing an explicit iterable overrides it (e.g. an operator watchlist).
    """
    source = CURATED_UNIVERSE if tickers is None else tuple(tickers)
    return tuple(sorted({t.strip().upper() for t in source if t.strip()}))


__all__ = ["CURATED_UNIVERSE", "resolve_universe"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_universe.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/universe.py services/api/tests/ml/test_ml_universe.py
git commit -m "add: curated ml universe resolution"
```

---

## Task 4: Bar extraction — pure transforms

**Files:**
- Create: `services/api/app/ml/extract/bars.py`
- Test: `services/api/tests/ml/test_ml_extract_bars.py`

This task adds only the pure (no-network) helpers: month-window splitting, response→DataFrame, and RTH tagging. The async fetch loop comes in Task 5 in the same file.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.ml.extract.bars import bars_response_to_frame, month_windows, tag_rth
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)


def test_month_windows_splits_inclusive_range() -> None:
    windows = month_windows(date(2025, 1, 15), date(2025, 3, 10))
    assert windows[0] == (date(2025, 1, 15), date(2025, 1, 31))
    assert windows[1] == (date(2025, 2, 1), date(2025, 2, 28))
    assert windows[-1] == (date(2025, 3, 1), date(2025, 3, 10))


def test_month_windows_single_month() -> None:
    assert month_windows(date(2025, 5, 1), date(2025, 5, 20)) == [
        (date(2025, 5, 1), date(2025, 5, 20))
    ]


def test_bars_response_to_frame_sorts_and_renames() -> None:
    response = PolygonAggregatesResponse(
        ticker="AAPL",
        queryCount=2,
        resultsCount=2,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(o=2.0, c=2.5, h=2.6, l=1.9, v=200.0, t=1700000300000),
            PolygonAggregateBar(o=1.0, c=1.5, h=1.6, l=0.9, v=100.0, t=1700000000000),
        ],
    )
    frame = bars_response_to_frame(response)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.is_monotonic_increasing
    assert frame.index.tz is not None
    assert frame["close"].tolist() == [1.5, 2.5]


def test_tag_rth_flags_only_regular_hours() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-02T13:00:00Z",  # 08:00 ET pre-market
            "2025-01-02T14:30:00Z",  # 09:30 ET open
            "2025-01-02T20:55:00Z",  # 15:55 ET
            "2025-01-02T21:00:00Z",  # 16:00 ET close (exclusive)
        ],
        tz="UTC",
    )
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    tagged = tag_rth(frame)
    assert tagged["is_rth"].tolist() == [False, True, True, False]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_bars.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation (pure helpers only)**

```python
from __future__ import annotations

import calendar
from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.services.market_clock import RTH_CLOSE_ET_MIN, RTH_OPEN_ET_MIN, to_et
from app.services.source_clients.polygon import PolygonAggregatesResponse

_COLUMNS = ["open", "high", "low", "close", "volume"]


def month_windows(from_date: date, to_date: date) -> list[tuple[date, date]]:
    """Split an inclusive [from_date, to_date] range into per-calendar-month windows.

    Keeps each Polygon aggregates request small enough to stay under the
    default 5000-row response cap for 5-minute bars (a month of extended-hours
    5-minute bars is well under that).
    """
    if from_date > to_date:
        raise ValueError("from_date must be <= to_date")
    windows: list[tuple[date, date]] = []
    cursor = from_date
    while cursor <= to_date:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        window_end = min(month_end, to_date)
        windows.append((cursor, window_end))
        if window_end.month == 12:
            cursor = date(window_end.year + 1, 1, 1)
        else:
            cursor = date(window_end.year, window_end.month + 1, 1)
    return windows


def bars_response_to_frame(response: PolygonAggregatesResponse) -> pd.DataFrame:
    """Convert a parsed Polygon aggregates response into a sorted OHLCV frame."""
    rows: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for bar in response.results:
        rows.append(
            {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
        timestamps.append(pd.Timestamp(bar.timestamp_ms, unit="ms", tz="UTC"))
    if not rows:
        return pd.DataFrame(
            {col: pd.Series(dtype="float64") for col in _COLUMNS},
            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"),
        )
    frame = pd.DataFrame(
        rows, index=pd.DatetimeIndex(timestamps, tz="UTC", name="timestamp")
    )
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[_COLUMNS]


def tag_rth(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `frame` with a boolean `is_rth` column (09:30–16:00 ET)."""
    flags = [
        RTH_OPEN_ET_MIN <= to_et(ts).minutes < RTH_CLOSE_ET_MIN for ts in frame.index
    ]
    out = frame.copy()
    out["is_rth"] = flags
    return out


__all__ = ["bars_response_to_frame", "month_windows", "tag_rth"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_bars.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/extract/bars.py services/api/tests/ml/test_ml_extract_bars.py
git commit -m "add: pure polygon bar transform helpers"
```

---

## Task 5: Bar extraction — async fetch loop

**Files:**
- Modify: `services/api/app/ml/extract/bars.py`
- Test: `services/api/tests/ml/test_ml_extract_bars.py` (append)

- [ ] **Step 1: Write the failing test (append to the existing test file)**

```python
import httpx
import respx

from app.ml.extract.bars import fetch_bars_for_ticker


@respx.mock
async def test_fetch_bars_for_ticker_concatenates_windows() -> None:
    def _payload(ts_ms: int, close: float) -> dict[str, object]:
        return {
            "ticker": "AAPL",
            "queryCount": 1,
            "resultsCount": 1,
            "adjusted": True,
            "status": "OK",
            "results": [{"o": 1.0, "c": close, "h": 2.0, "l": 0.5, "v": 10.0, "t": ts_ms}],
        }

    respx.get(url__regex=r".*/range/5/minute/2025-01-01/2025-01-31.*").mock(
        return_value=httpx.Response(200, json=_payload(1735830000000, 10.0))
    )
    respx.get(url__regex=r".*/range/5/minute/2025-02-01/2025-02-15.*").mock(
        return_value=httpx.Response(200, json=_payload(1738500000000, 20.0))
    )

    async with httpx.AsyncClient() as client:
        frame = await fetch_bars_for_ticker(
            client=client,
            ticker="AAPL",
            from_date=date(2025, 1, 1),
            to_date=date(2025, 2, 15),
        )

    assert len(frame) == 2
    assert frame.index.is_monotonic_increasing
    assert "is_rth" in frame.columns
    assert frame["close"].tolist() == [10.0, 20.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_bars.py::test_fetch_bars_for_ticker_concatenates_windows -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_bars_for_ticker'`.

- [ ] **Step 3: Add the fetch loop to `bars.py`**

Add these imports at the top of `bars.py`:

```python
import httpx
import structlog

from app.services.source_clients.polygon import fetch_polygon_aggregates

logger = structlog.get_logger(__name__)
```

Add the function:

```python
async def fetch_bars_for_ticker(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    adjusted: bool = True,
) -> pd.DataFrame:
    """Fetch all 5-minute bars for `ticker` over [from_date, to_date], RTH-tagged.

    Iterates month windows so each request stays under Polygon's default row
    cap, concatenates the parsed frames, deduplicates, and tags RTH. Windows
    that return no rows are skipped. The shared Polygon rate limiter inside
    `fetch_polygon_aggregates` paces the requests.
    """
    frames: list[pd.DataFrame] = []
    for window_start, window_end in month_windows(from_date, to_date):
        response, _ = await fetch_polygon_aggregates(
            client=client,
            ticker=ticker,
            multiplier=5,
            timespan="minute",
            from_date=window_start,
            to_date=window_end,
            adjusted=adjusted,
        )
        window_frame = bars_response_to_frame(response)
        if not window_frame.empty:
            frames.append(window_frame)
    if not frames:
        logger.warning("no_bars_fetched", ticker=ticker)
        empty = bars_response_to_frame(
            PolygonAggregatesResponse(
                ticker=ticker,
                queryCount=0,
                resultsCount=0,
                adjusted=adjusted,
                status="OK",
                results=[],
            )
        )
        return tag_rth(empty)
    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return tag_rth(combined)
```

Add `"fetch_bars_for_ticker"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_bars.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/extract/bars.py services/api/tests/ml/test_ml_extract_bars.py
git commit -m "add: polygon 5min bar fetch loop with month-window pagination"
```

---

## Task 6: Price/volume features

**Files:**
- Create: `services/api/app/ml/features/price.py`
- Test: `services/api/tests/ml/test_ml_features_price.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig
from app.ml.features.price import build_price_features


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    close = pd.Series(np.linspace(100.0, 110.0, n), index=idx)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]).to_numpy(),
            "high": (close + 0.5).to_numpy(),
            "low": (close - 0.5).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_price_features_have_expected_columns() -> None:
    feats = build_price_features(_frame(60), FeatureConfig())
    for window in (1, 3, 6, 12):
        assert f"ret_{window}" in feats.columns
    assert "hl_range" in feats.columns
    assert "gap_prev_close" in feats.columns
    assert "rel_volume" in feats.columns
    assert "realized_vol" in feats.columns


def test_log_return_one_bar_matches_manual() -> None:
    feats = build_price_features(_frame(10), FeatureConfig())
    frame = _frame(10)
    expected = np.log(frame["close"].iloc[5] / frame["close"].iloc[4])
    assert abs(feats["ret_1"].iloc[5] - expected) < 1e-9


def test_price_features_index_aligns_with_input() -> None:
    frame = _frame(30)
    feats = build_price_features(frame, FeatureConfig())
    assert feats.index.equals(frame.index)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_price.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig


def build_price_features(bars: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Causal price/volume features aligned to `bars.index`.

    Every value at bar t uses only data at or before t. Warmup positions are
    NaN and are dropped later during assembly.
    """
    close = bars["close"].astype("float64")
    out = pd.DataFrame(index=bars.index)

    log_close = np.log(close)
    for window in config.return_windows:
        out[f"ret_{window}"] = log_close.diff(window)

    out["hl_range"] = (bars["high"] - bars["low"]) / close
    out["co_change"] = (close - bars["open"]) / bars["open"]
    out["gap_prev_close"] = close / close.shift(1) - 1.0

    volume = bars["volume"].astype("float64")
    rolling_volume = volume.rolling(
        config.relative_volume_window, min_periods=config.relative_volume_window
    ).mean()
    out["rel_volume"] = volume / rolling_volume

    one_bar_ret = log_close.diff(1)
    out["realized_vol"] = one_bar_ret.rolling(
        config.realized_vol_window, min_periods=config.realized_vol_window
    ).std()

    return out


__all__ = ["build_price_features"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_price.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/features/price.py services/api/tests/ml/test_ml_features_price.py
git commit -m "add: causal price and volume features"
```

---

## Task 7: Technical features (wrap app.indicators)

**Files:**
- Create: `services/api/app/ml/features/technical.py`
- Test: `services/api/tests/ml/test_ml_features_technical.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import FeatureConfig
from app.ml.features.technical import build_technical_features


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(0)
    steps = rng.normal(0, 0.3, n).cumsum()
    close = pd.Series(100.0 + steps, index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.6).to_numpy(),
            "low": (close - 0.6).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_technical_features_have_expected_columns() -> None:
    feats = build_technical_features(_frame(120), FeatureConfig())
    for col in (
        "rsi",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "adx",
        "atr",
        "bb_pct",
        "ema_fast_ratio",
        "ema_slow_ratio",
    ):
        assert col in feats.columns


def test_technical_features_align_to_input_index() -> None:
    frame = _frame(120)
    feats = build_technical_features(frame, FeatureConfig())
    assert feats.index.equals(frame.index)


def test_atr_column_matches_indicator_wrapper() -> None:
    from app.indicators import atr

    frame = _frame(120)
    feats = build_technical_features(frame, FeatureConfig())
    expected = atr(frame, period=14)
    pd.testing.assert_series_equal(
        feats["atr"], expected, check_names=False
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_technical.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
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

    middle, upper, lower = bollinger(
        close, period=config.bollinger_period, mult=config.bollinger_mult
    )
    band_width = (upper - lower).replace(0.0, float("nan"))
    out["bb_pct"] = (close - lower) / band_width

    out["ema_fast_ratio"] = close / ema(close, period=config.ema_fast) - 1.0
    out["ema_slow_ratio"] = close / ema(close, period=config.ema_slow) - 1.0

    return out


__all__ = ["build_technical_features"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_technical.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/features/technical.py services/api/tests/ml/test_ml_features_technical.py
git commit -m "add: technical indicator features over app.indicators"
```

---

## Task 8: Session/time features

**Files:**
- Create: `services/api/app/ml/features/session.py`
- Test: `services/api/tests/ml/test_ml_features_session.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.ml.features.session import build_session_features


def test_session_features_minutes_since_open() -> None:
    idx = pd.DatetimeIndex(
        ["2025-01-02T14:30:00Z", "2025-01-02T15:00:00Z", "2025-01-02T20:55:00Z"],
        tz="UTC",
    )
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=idx)
    feats = build_session_features(frame)
    assert feats["minutes_since_open"].tolist() == [0, 30, 385]
    assert feats["is_first_30min"].tolist() == [True, True, False]
    assert feats["is_last_30min"].tolist() == [False, False, True]


def test_session_features_day_of_week() -> None:
    idx = pd.DatetimeIndex(["2025-01-02T15:00:00Z"], tz="UTC")  # Thursday
    frame = pd.DataFrame({"close": [1.0]}, index=idx)
    feats = build_session_features(frame)
    assert feats["day_of_week"].iloc[0] == 3


def test_session_features_align_to_index() -> None:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=10, freq="5min", tz="UTC")
    frame = pd.DataFrame({"close": range(10)}, index=idx)
    feats = build_session_features(frame)
    assert feats.index.equals(frame.index)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_session.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]

from app.services.market_clock import RTH_CLOSE_ET_MIN, RTH_OPEN_ET_MIN, to_et

_ET = ZoneInfo("America/New_York")


def build_session_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Session/time-of-day features aligned to `bars.index` (UTC DatetimeIndex)."""
    minutes_since_open: list[int] = []
    day_of_week: list[int] = []
    for ts in bars.index:
        clock = to_et(ts)
        minutes_since_open.append(clock.minutes - RTH_OPEN_ET_MIN)
        day_of_week.append(ts.astimezone(_ET).weekday())

    out = pd.DataFrame(index=bars.index)
    out["minutes_since_open"] = minutes_since_open
    out["day_of_week"] = day_of_week
    out["is_first_30min"] = [0 <= m < 30 for m in minutes_since_open]
    last_30_start = (RTH_CLOSE_ET_MIN - RTH_OPEN_ET_MIN) - 30
    out["is_last_30min"] = [m >= last_30_start for m in minutes_since_open]
    return out


__all__ = ["build_session_features"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_session.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/features/session.py services/api/tests/ml/test_ml_features_session.py
git commit -m "add: session and time-of-day features"
```

---

## Task 9: Causal per-ticker normalization

**Files:**
- Create: `services/api/app/ml/features/normalize.py`
- Test: `services/api/tests/ml/test_ml_features_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.features.normalize import causal_zscore


def test_zscore_is_nan_before_min_periods() -> None:
    s = pd.Series(np.arange(100, dtype="float64"))
    z = causal_zscore(s, window=20, min_periods=10)
    assert z.iloc[:9].isna().all()
    assert not np.isnan(z.iloc[50])


def test_zscore_uses_only_past_and_current() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 100.0, 5.0, 6.0])
    z = causal_zscore(s, window=10, min_periods=2)
    later = pd.Series([1.0, 2.0, 3.0, 100.0, 999.0, 6.0])
    z_later = causal_zscore(later, window=10, min_periods=2)
    assert z.iloc[3] == z_later.iloc[3]


def test_zscore_constant_window_yields_zero_not_inf() -> None:
    s = pd.Series([5.0] * 30)
    z = causal_zscore(s, window=10, min_periods=5)
    assert np.isfinite(z.iloc[-1])
    assert z.iloc[-1] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd  # type: ignore[import-untyped]


def causal_zscore(series: pd.Series, *, window: int, min_periods: int) -> pd.Series:
    """Rolling z-score using only past-and-current values (no look-ahead).

    The rolling window ending at bar t includes t, all of whose inputs are
    known at t. A zero rolling std (constant window) yields 0.0, never inf.
    Positions with fewer than `min_periods` observations are NaN.
    """
    rolling = series.rolling(window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0)
    z = (series - mean) / std
    z = z.where(std != 0.0, 0.0)
    z = z.where(~mean.isna(), other=float("nan"))
    return z


def normalize_columns(
    frame: pd.DataFrame, columns: Iterable[str], *, window: int, min_periods: int
) -> pd.DataFrame:
    """Return a copy of `frame` with `columns` replaced by their causal z-scores."""
    out = frame.copy()
    for column in columns:
        out[column] = causal_zscore(
            frame[column].astype("float64"), window=window, min_periods=min_periods
        )
    return out


__all__ = ["causal_zscore", "normalize_columns"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_normalize.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/features/normalize.py services/api/tests/ml/test_ml_features_normalize.py
git commit -m "add: causal rolling z-score normalization"
```

---

## Task 10: Triple-barrier labeler (crown jewel)

**Files:**
- Create: `services/api/app/ml/labels/triple_barrier.py`
- Test: `services/api/tests/ml/test_ml_labels_triple_barrier.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import BarrierConfig
from app.ml.labels.triple_barrier import label_triple_barrier


def _session_frame(closes: list[float], highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_upper_barrier_hit_first_labels_1() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    highs[5] = 105.0  # large up-spike within horizon
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 1
    assert labels.loc[frame.index[0], "touch_type"] == "upper"


def test_lower_barrier_hit_first_labels_0() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    lows[3] = 98.0  # down-spike crosses -1*ATR before any up-move
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "lower"


def test_no_touch_within_horizon_is_vertical_zero() -> None:
    closes = [100.0] * 20
    highs = [100.2] * 20
    lows = [99.8] * 20
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=5)
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "vertical"


def test_session_tail_rows_are_unlabeled() -> None:
    closes = [100.0] * 6
    highs = [100.2] * 6
    lows = [99.8] * 6
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    # last bar has no future bars in-session -> NaN label
    assert pd.isna(labels.loc[frame.index[-1], "barrier_label"])


def test_ambiguous_bar_resolves_lower_first() -> None:
    closes = [100.0] * 20
    highs = [100.5] * 20
    lows = [99.5] * 20
    highs[2] = 105.0  # same bar crosses both barriers
    lows[2] = 97.0
    frame = _session_frame(closes, highs, lows)
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12,
                                  ambiguous_bar_resolution="lower_first")
    )
    assert labels.loc[frame.index[0], "barrier_label"] == 0
    assert labels.loc[frame.index[0], "touch_type"] == "lower"


def test_vertical_barrier_does_not_cross_session_boundary() -> None:
    # two sessions back-to-back; entry near end of session 1 must time out at
    # session-1 close, never peek into session 2's bars
    idx1 = pd.date_range("2025-01-02T20:30:00Z", periods=6, freq="5min", tz="UTC")  # ends 15:55 ET
    idx2 = pd.date_range("2025-01-03T14:30:00Z", periods=6, freq="5min", tz="UTC")
    idx = idx1.append(idx2)
    closes = [100.0] * 12
    highs = [100.2] * 6 + [200.0] * 6  # session 2 has a huge spike
    lows = [99.8] * 12
    frame = pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes,
         "volume": [1000.0] * 12, "is_rth": [True] * 12},
        index=idx,
    )
    atr = pd.Series(1.0, index=frame.index)
    labels = label_triple_barrier(
        frame, atr, BarrierConfig(pt_mult=2.0, sl_mult=1.0, horizon_bars=12)
    )
    # entry at first session-1 bar must NOT be labeled 1 from session-2 spike
    assert labels.loc[idx1[0], "touch_type"] in ("vertical", "lower")
    assert labels.loc[idx1[0], "barrier_label"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_labels_triple_barrier.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import BarrierConfig
from app.services.market_clock import to_et

_LABEL_COLUMNS = [
    "barrier_label",
    "touch_type",
    "label_return",
    "label_end_ts",
    "atr_at_entry",
]


def label_triple_barrier(
    bars: pd.DataFrame, atr_at_entry: pd.Series, config: BarrierConfig
) -> pd.DataFrame:
    """Session-aware, ATR-scaled triple-barrier labels aligned to `bars.index`.

    For each entry bar t with finite ATR, scan strictly-later bars within the
    same ET session, capped at t + horizon_bars. The first barrier touched
    wins: upper (close_t + pt_mult*ATR) -> label 1; lower
    (close_t - sl_mult*ATR) -> label 0; neither by the cap -> vertical, label 0.
    A single bar straddling both barriers is resolved by
    `config.ambiguous_bar_resolution`. Rows whose ATR is NaN or which have no
    in-session future bar are left unlabeled (NaN).
    """
    closes = bars["close"].to_numpy(dtype="float64")
    highs = bars["high"].to_numpy(dtype="float64")
    lows = bars["low"].to_numpy(dtype="float64")
    atr_values = atr_at_entry.to_numpy(dtype="float64")
    session_days = [to_et(ts).day for ts in bars.index]
    n = len(bars)

    labels: list[float] = [float("nan")] * n
    touch_types: list[object] = [None] * n
    label_returns: list[float] = [float("nan")] * n
    label_end: list[object] = [None] * n

    for i in range(n):
        atr_i = atr_values[i]
        if not np.isfinite(atr_i) or atr_i <= 0.0:
            continue
        upper = closes[i] + config.pt_mult * atr_i
        lower = closes[i] - config.sl_mult * atr_i
        last_j = min(i + config.horizon_bars, n - 1)
        resolved = False
        for j in range(i + 1, last_j + 1):
            if session_days[j] != session_days[i]:
                last_j = j - 1
                break
            hit_upper = highs[j] >= upper
            hit_lower = lows[j] <= lower
            if hit_upper and hit_lower:
                if config.ambiguous_bar_resolution == "lower_first":
                    labels[i], touch_types[i] = 0.0, "lower"
                else:
                    labels[i], touch_types[i] = 1.0, "upper"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
            if hit_upper:
                labels[i], touch_types[i] = 1.0, "upper"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
            if hit_lower:
                labels[i], touch_types[i] = 0.0, "lower"
                label_returns[i] = closes[j] / closes[i] - 1.0
                label_end[i] = bars.index[j]
                resolved = True
                break
        if resolved:
            continue
        if last_j > i:
            labels[i], touch_types[i] = 0.0, "vertical"
            label_returns[i] = closes[last_j] / closes[i] - 1.0
            label_end[i] = bars.index[last_j]

    out = pd.DataFrame(index=bars.index)
    out["barrier_label"] = labels
    out["touch_type"] = touch_types
    out["label_return"] = label_returns
    out["label_end_ts"] = label_end
    out["atr_at_entry"] = atr_values
    return out[_LABEL_COLUMNS]


__all__ = ["label_triple_barrier"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_labels_triple_barrier.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/labels/triple_barrier.py services/api/tests/ml/test_ml_labels_triple_barrier.py
git commit -m "add: session-aware atr-scaled triple-barrier labeler"
```

---

## Task 11: Assembly (per-ticker build + concat + manifest)

**Files:**
- Create: `services/api/app/ml/assemble.py`
- Test: `services/api/tests/ml/test_ml_assemble.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import EtlConfig, FeatureConfig
from app.ml.assemble import build_ticker_dataset, feature_columns


def _bars(n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(1)
    close = pd.Series(100.0 + rng.normal(0, 0.4, n).cumsum(), index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.7).to_numpy(),
            "low": (close - 0.7).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_build_ticker_dataset_has_label_and_features_no_nan() -> None:
    bars = _bars(200)
    frame = build_ticker_dataset("AAPL", bars, EtlConfig(
        tickers=("AAPL",), from_date=bars.index[0].date(), to_date=bars.index[-1].date()
    ))
    assert "ticker" in frame.columns
    assert (frame["ticker"] == "AAPL").all()
    assert "barrier_label" in frame.columns
    assert frame["barrier_label"].notna().all()
    for col in feature_columns(FeatureConfig()):
        assert frame[col].notna().all()


def test_build_ticker_dataset_is_deterministic() -> None:
    bars = _bars(200)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    a = build_ticker_dataset("AAPL", bars, cfg)
    b = build_ticker_dataset("AAPL", bars, cfg)
    pd.testing.assert_frame_equal(a, b)


def test_feature_columns_excludes_label_and_meta() -> None:
    cols = feature_columns(FeatureConfig())
    for forbidden in ("barrier_label", "touch_type", "label_return", "ticker",
                      "label_end_ts", "atr_at_entry", "is_rth"):
        assert forbidden not in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_assemble.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from app.indicators import atr
from app.ml.config import EtlConfig, FeatureConfig
from app.ml.features.normalize import normalize_columns
from app.ml.features.price import build_price_features
from app.ml.features.session import build_session_features
from app.ml.features.technical import build_technical_features
from app.ml.labels.triple_barrier import label_triple_barrier
from app.ml.storage import write_json, write_parquet

_META_COLUMNS = [
    "ticker",
    "barrier_label",
    "touch_type",
    "label_return",
    "label_end_ts",
    "atr_at_entry",
]

_NORMALIZE_COLUMNS = (
    "macd_line",
    "macd_signal",
    "macd_hist",
    "atr",
    "realized_vol",
    "hl_range",
)


def feature_columns(config: FeatureConfig) -> list[str]:
    """The ordered list of model-facing feature columns (no label/meta)."""
    cols: list[str] = [f"ret_{w}" for w in config.return_windows]
    cols += ["hl_range", "co_change", "gap_prev_close", "rel_volume", "realized_vol"]
    cols += [
        "rsi", "macd_line", "macd_signal", "macd_hist", "adx", "atr",
        "bb_pct", "ema_fast_ratio", "ema_slow_ratio",
    ]
    cols += ["minutes_since_open", "day_of_week", "is_first_30min", "is_last_30min"]
    return cols


def build_ticker_dataset(
    ticker: str, bars: pd.DataFrame, config: EtlConfig
) -> pd.DataFrame:
    """Build a labeled, feature-complete dataset for one ticker (RTH bars only)."""
    rth = bars[bars["is_rth"]] if config.rth_only else bars
    rth = rth.sort_index()

    price = build_price_features(rth, config.features)
    technical = build_technical_features(rth, config.features)
    session = build_session_features(rth)
    atr_series = atr(rth, period=config.barrier.atr_period)
    labels = label_triple_barrier(rth, atr_series, config.barrier)

    features = pd.concat([price, technical, session], axis=1)
    features = normalize_columns(
        features,
        _NORMALIZE_COLUMNS,
        window=config.features.normalize_window,
        min_periods=config.features.normalize_min_periods,
    )

    combined = pd.concat([features, labels], axis=1)
    combined.insert(0, "ticker", ticker)
    combined = combined[feature_columns(config.features) + _META_COLUMNS]

    feature_only = combined[feature_columns(config.features)]
    combined = combined[
        feature_only.notna().all(axis=1) & combined["barrier_label"].notna()
    ]
    combined = combined.reset_index().rename(columns={"timestamp": "entry_ts"})
    combined["session_date"] = combined["entry_ts"].dt.tz_convert(
        "America/New_York"
    ).dt.date.astype(str)
    return combined.sort_values(["ticker", "entry_ts"]).reset_index(drop=True)


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def assemble_dataset(
    run_id: str,
    per_ticker: dict[str, pd.DataFrame],
    config: EtlConfig,
) -> Path:
    """Concatenate per-ticker datasets, write dataset.parquet + manifest + spec."""
    frames = [frame for frame in per_ticker.values() if not frame.empty]
    dataset = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=feature_columns(config.features) + _META_COLUMNS)
    )
    out_dir = config.paths.dataset_dir(run_id)
    write_parquet(dataset, out_dir / "dataset.parquet")

    label_balance: dict[str, Any] = (
        dataset["barrier_label"].value_counts().to_dict() if not dataset.empty else {}
    )
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "git_sha": _git_sha(),
        "from_date": config.from_date,
        "to_date": config.to_date,
        "rth_only": config.rth_only,
        "barrier": vars(config.barrier),
        "tickers": list(per_ticker.keys()),
        "row_counts": {t: int(len(f)) for t, f in per_ticker.items()},
        "total_rows": int(len(dataset)),
        "label_balance": {str(k): int(v) for k, v in label_balance.items()},
    }
    write_json(manifest, out_dir / "manifest.json")

    spec: dict[str, Any] = {
        "features": feature_columns(config.features),
        "normalized": list(_NORMALIZE_COLUMNS),
        "label": "barrier_label",
    }
    write_json(spec, out_dir / "feature_spec.json")
    return out_dir


__all__ = [
    "assemble_dataset",
    "build_ticker_dataset",
    "feature_columns",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_assemble.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/assemble.py services/api/tests/ml/test_ml_assemble.py
git commit -m "add: per-ticker dataset assembly with manifest and feature spec"
```

---

## Task 12: CLI

**Files:**
- Create: `services/api/app/ml/cli.py`
- Test: `services/api/tests/ml/test_ml_cli.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from typer.testing import CliRunner

from app.ml.cli import app
from app.ml.config import PathConfig
from app.ml.storage import write_parquet

runner = CliRunner()


def _write_raw(paths: PathConfig, ticker: str) -> None:
    n = 220
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(2)
    close = pd.Series(100.0 + rng.normal(0, 0.4, n).cumsum(), index=idx)
    frame = pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.7).to_numpy(),
            "low": (close - 0.7).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )
    write_parquet(frame, paths.raw_bars_path(ticker))


def test_build_dataset_from_cached_bars(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    _write_raw(paths, "AAPL")
    result = runner.invoke(
        app,
        [
            "build-dataset",
            "--ticker", "AAPL",
            "--from-date", "2025-01-02",
            "--to-date", "2025-01-03",
            "--run-id", "testrun",
            "--root", str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    dataset = pd.read_parquet(paths.dataset_dir("testrun") / "dataset.parquet")
    assert len(dataset) > 0
    assert (paths.dataset_dir("testrun") / "manifest.json").exists()
    assert (paths.dataset_dir("testrun") / "feature_spec.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import httpx
import structlog
import typer

from app.ml.assemble import assemble_dataset, build_ticker_dataset
from app.ml.config import EtlConfig, PathConfig
from app.ml.extract.bars import fetch_bars_for_ticker
from app.ml.storage import read_parquet, write_parquet
from app.ml.universe import resolve_universe

logger = structlog.get_logger(__name__)
app = typer.Typer(no_args_is_help=True)


def _config(
    tickers: tuple[str, ...], from_date: date, to_date: date, root: Path
) -> EtlConfig:
    return EtlConfig(
        tickers=tickers,
        from_date=from_date,
        to_date=to_date,
        paths=PathConfig(root=root),
    )


@app.command("pull-bars")
def pull_bars(
    ticker: list[str] = typer.Option(None, "--ticker"),
    from_date: datetime_date := typer.Option(..., "--from-date"),  # see note
    to_date: datetime_date := typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),
) -> None:
    """Fetch and cache raw 5-minute bars for the universe to parquet."""
    universe = resolve_universe(ticker or None)
    paths = PathConfig(root=root)

    async def _run() -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for symbol in universe:
                frame = await fetch_bars_for_ticker(
                    client=client, ticker=symbol, from_date=from_date, to_date=to_date
                )
                write_parquet(frame, paths.raw_bars_path(symbol))
                logger.info("pulled_bars", ticker=symbol, rows=int(len(frame)))

    asyncio.run(_run())


@app.command("build-dataset")
def build_dataset(
    run_id: str = typer.Option(..., "--run-id"),
    ticker: list[str] = typer.Option(None, "--ticker"),
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),
) -> None:
    """Build a labeled dataset from already-cached raw bars."""
    universe = resolve_universe(ticker or None)
    config = _config(universe, date.fromisoformat(from_date), date.fromisoformat(to_date), root)
    per_ticker: dict[str, "object"] = {}
    for symbol in universe:
        raw_path = config.paths.raw_bars_path(symbol)
        if not raw_path.exists():
            logger.warning("missing_raw_bars", ticker=symbol)
            continue
        bars = read_parquet(raw_path)
        per_ticker[symbol] = build_ticker_dataset(symbol, bars, config)
    out_dir = assemble_dataset(run_id, per_ticker, config)
    typer.echo(str(out_dir))


__all__ = ["app"]
```

> **Note for the implementer:** the `pull-bars` signature above shows intent but uses
> invalid walrus syntax in defaults — write the date options the same plain way as
> `build-dataset` (accept `str`, parse with `date.fromisoformat`). Corrected `pull-bars`
> options:
> ```python
> from_date: str = typer.Option(..., "--from-date"),
> to_date: str = typer.Option(..., "--to-date"),
> ```
> and inside `_run`, parse once: `start = date.fromisoformat(from_date)`,
> `end = date.fromisoformat(to_date)`, passing those to `fetch_bars_for_ticker`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_cli.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/cli.py services/api/tests/ml/test_ml_cli.py
git commit -m "add: alphora-etl cli with pull-bars and build-dataset"
```

---

## Task 13: Integration — leakage invariant + determinism

**Files:**
- Test: `services/api/tests/ml/test_ml_integration.py`

This task adds no new production code; it asserts the spec's leakage invariants
(§9) and end-to-end determinism on the assembled pipeline.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.assemble import build_ticker_dataset, feature_columns
from app.ml.config import EtlConfig, FeatureConfig


def _bars(n: int, seed: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02T14:30:00Z", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = pd.Series(100.0 + rng.normal(0, 0.5, n).cumsum(), index=idx)
    return pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 0.8).to_numpy(),
            "low": (close - 0.8).to_numpy(),
            "close": close.to_numpy(),
            "volume": np.full(n, 1000.0),
            "is_rth": [True] * n,
        },
        index=idx,
    )


def test_label_end_is_strictly_after_entry() -> None:
    bars = _bars(220, 3)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    ds = build_ticker_dataset("AAPL", bars, cfg)
    labeled = ds[ds["label_end_ts"].notna()]
    assert (labeled["label_end_ts"] > labeled["entry_ts"]).all()


def test_modifying_future_bars_never_changes_past_features() -> None:
    bars = _bars(220, 4)
    cfg = EtlConfig(tickers=("AAPL",), from_date=bars.index[0].date(),
                    to_date=bars.index[-1].date())
    base = build_ticker_dataset("AAPL", bars, cfg)

    tampered = bars.copy()
    tampered.iloc[180:, tampered.columns.get_loc("close")] *= 1.5
    tampered.iloc[180:, tampered.columns.get_loc("high")] *= 1.5
    after = build_ticker_dataset("AAPL", tampered, cfg)

    cutoff = base["entry_ts"].iloc[100]
    cols = feature_columns(FeatureConfig())
    base_head = base[base["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    after_head = after[after["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_head, after_head)
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_integration.py -v`
Expected: PASS (production code already exists). If `test_modifying_future_bars_never_changes_past_features` fails, a feature is using look-ahead — fix the offending feature in `features/` before proceeding. This is the most important guard in the suite.

- [ ] **Step 3: Run the full ml suite + type check + lint**

```bash
cd services/api
uv run pytest tests/ml/ -v
uv run mypy app/ml
uv run ruff check app/ml tests/ml
```
Expected: all tests pass, mypy clean, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/ml/test_ml_integration.py
git commit -m "add: ml pipeline leakage and determinism integration tests"
```

---

## Self-review (completed against spec)

- **Spec §4 module layout** → Tasks 0–12 create the listed modules (context/ deferred to Plan B, called out).
- **Spec §5.1 universe** → Task 3. **§5.2 raw bars (pagination, RTH, idempotent)** → Tasks 4–5 + CLI `pull-bars`.
- **Spec §5.3 context extraction / §6 context features** → **Plan B** (explicitly deferred; this plan is independently trainable from the price spine).
- **Spec §6 price/technical/session/normalization** → Tasks 6–9.
- **Spec §7 triple-barrier (defaults, session cap, ambiguous bar, touch_type/label_return/label_end_ts/atr_at_entry)** → Task 10.
- **Spec §8 output schema + manifest + feature_spec** → Task 11.
- **Spec §9 leakage invariants** → Task 13 (`test_modifying_future_bars_never_changes_past_features`, `test_label_end_is_strictly_after_entry`) + Task 10 session-boundary test.
- **Spec §10 tests** → each task is TDD; integration in Task 13.
- **Spec §11 deps/CLI/config** → Task 0 (pyarrow extra, script), Task 12 (CLI), Task 1 (config).
- **Placeholder scan:** no TBD/TODO left. The one risky spot — the `pull-bars` signature — is flagged with an explicit correction note rather than left ambiguous.
- **Type consistency:** `feature_columns(FeatureConfig)`, `build_ticker_dataset(ticker, bars, EtlConfig)`, `label_triple_barrier(bars, atr_series, BarrierConfig)`, `causal_zscore(series, *, window, min_periods)`, `fetch_bars_for_ticker(*, client, ticker, from_date, to_date)` are used consistently across tasks.

---

## Follow-up: Plan B (context layer)

To be authored next, after verifying each context fetcher signature
(`fetch_finnhub_insider_transactions`, `fetch_finnhub_company_news`,
`fetch_finnhub_recommendation_trends`, Tiingo/GDELT/FRED equivalents). Plan B adds:
- `extract/context.py` — reuse existing source clients → per-source timestamped event parquet.
- `features/context_join.py` — backward `merge_asof` (rolling counts for news, forward-fill for recommendation/FRED, recency/intensity for insider).
- New normalized context columns appended in `assemble.py` and `feature_spec.json`.
- Context-specific leakage tests (an event dated after a bar never appears in that bar's row).
