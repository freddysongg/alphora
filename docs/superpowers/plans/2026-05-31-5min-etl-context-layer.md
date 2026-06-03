# 5-min ETL Context Layer Implementation Plan (Plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Layer point-in-time-safe cross-source context features (insider transactions, company-news volume, analyst-recommendation trend, FRED macro) onto the Plan A price-spine dataset, joined to the 5-minute bar grid by strictly-backward as-of merges so no event timestamped after a bar ever appears in that bar's row.

**Architecture:** New `app/ml/extract/context.py` (async fetch of the existing Finnhub/FRED source clients → per-source timestamped event parquet under `data/ml/context/`) and `app/ml/features/context_join.py` (pure, vectorized as-of joins / rolling counts onto a bar `DatetimeIndex`). Context is **opt-in**: `EtlConfig.context` defaults to `None`, so every Plan A test and the crown-jewel leakage guard keep passing unchanged. When context is enabled, `assemble.build_ticker_dataset` appends the normalized context columns; `assemble_dataset` records them in `feature_spec.json` / `manifest.json`; the CLI gains `pull-context` and a `build-dataset --with-context` flag.

**Tech Stack:** Python 3.12, pandas, numpy, pyarrow, httpx, typer, pytest + pytest-asyncio (`asyncio_mode = "auto"`) + respx. mypy `strict`, ruff (`E,F,I,B,UP,N,RUF`).

**Spec:** `docs/superpowers/specs/2026-05-31-5min-etl-feature-pipeline-design.md` (§5.3 context extraction, §6 Context family, §9 leakage invariants, §10 tests, §12 excluded snapshot sources).

**Plan A (prerequisite, complete):** `docs/superpowers/plans/2026-05-31-5min-etl-core-spine.md`.

---

## Resolved decisions (locked for this plan)

These resolve genuine mismatches between the spec's source list and what the source clients can actually do point-in-time. They were chosen as the simplest fully-PIT-safe v1; the structure leaves room to add the deferred sources later.

1. **FRED — lag heuristic on non-revised daily series.** `fetch_series_observations` exposes no `realtime_start`/`realtime_end` request params, so it returns latest-revised observations (`realtime_start` = today); the spec's literal "`realtime_start ≤ bar date`" rule would drop every historical row. Instead we restrict FRED to **non-revised daily market series** (default `("DGS10", "VIXCLS", "T10Y2Y")`) and treat each observation's *event time* as `observation_date + fred_lag_days` (default 1), forward-filled. These series are never revised, so there is no revision leak, and the +1-day lag guarantees a value dated D only appears on bars from the next session onward. No change to the shared source client. (Deferred alternative: true ALFRED vintages via a `fetch_series_observations` extension — out of scope here.)

2. **News volume — Finnhub company-news only for v1.** `fetch_finnhub_company_news` keys cleanly by ticker and accepts real `from`/`to` date windows, so it backfills historical rolling counts safely. `fetch_tiingo_news` has **no date-range params** (only `limit`/`tickers`) and cannot backfill historical windows, and GDELT keys by free-text keyword (needs a ticker→company-name map). Both are deferred. `context_join` is written so adding more `published_ts` rows later (GDELT/Tiingo) is purely additive.

3. **Insider / recommendation event times.** Insider transactions become known at their **filing date** → event time `filing_date + insider_lag_days` (default 1). Finnhub recommendation `period` is a monthly aggregate that Finnhub keeps updating through the month; to avoid intra-month look-ahead the month-`P` aggregate is treated as known only from the **start of month P+1** (`recommendation_lag_days` default 0 applied to the next-month-start date).

4. **Context features are always-defined** (so "no signal yet" never wipes out rows via the NaN-drop gate): news/insider-net counts default to `0`, insider recency defaults to a config cap, recommendation net-score defaults to `0.0`. The one exception is FRED **level**, which is genuinely undefined before the first available observation; `pull-context` fetches `fred_history_days` (default 365) of history before `from_date` so in practice every in-window bar has a prior observation, and any residual leading-NaN rows drop safely (never leak).

---

## File structure

```
services/api/app/ml/
  config.py            # MODIFY: + ContextConfig; PathConfig.context_path; EtlConfig.context
  extract/
    context.py         # CREATE: available_utc + per-source response->event-frame transforms + async pull_* loops
  features/
    context_join.py    # CREATE: ContextBundle, load_context_bundle, as-of/rolling-count builders, build_context_features, column helpers
  assemble.py          # MODIFY: all_feature_columns; build_ticker_dataset(context=...); context-aware spec/manifest
  cli.py               # MODIFY: pull-context command; build-dataset --with-context

services/api/tests/ml/
  test_ml_config.py            # MODIFY: ContextConfig + PathConfig context paths + EtlConfig.context default
  test_ml_extract_context.py   # CREATE: transforms (Task 2) + async respx fetch (Task 3)
  test_ml_features_context_join.py  # CREATE: join correctness + leakage + load roundtrip (Task 4)
  test_ml_assemble.py          # MODIFY: context columns / determinism / guard (Task 5)
  test_ml_cli.py               # MODIFY: pull-context + build-dataset --with-context (Task 6)
  test_ml_integration.py       # MODIFY: context leakage + determinism with context (Task 7)
```

**Conventions to match (verified in repo):**
- Every module starts with `from __future__ import annotations`.
- pandas import line: `import pandas as pd  # type: ignore[import-untyped]`.
- Frozen dataclasses for config; explicit return types everywhere (mypy strict); **no bare `np.ndarray` in public signatures** (use `pd.DatetimeIndex` / `pd.Series` / `pd.DataFrame`; numpy arrays stay local).
- typer options annotated `list[str] | None` or `Path` with a `typer.Option(...)` default need `# noqa: B008` (scalar `str`/`bool` options do not).
- Source-client tests set the relevant key via `monkeypatch.setenv(...)` + `get_settings.cache_clear()`; the ml `conftest.py` already sets `POLYGON_API_KEY`.

---

## Task 1: ContextConfig + PathConfig context paths + EtlConfig.context

**Files:**
- Modify: `services/api/app/ml/config.py`
- Test: `services/api/tests/ml/test_ml_config.py` (append)

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
def test_context_config_defaults() -> None:
    from app.ml.config import ContextConfig

    cfg = ContextConfig()
    assert cfg.insider_net_window_days == 30
    assert cfg.insider_recency_cap_days == 252.0
    assert cfg.insider_lag_days == 1
    assert cfg.news_count_windows_days == (1, 5, 20)
    assert cfg.recommendation_lag_days == 0
    assert cfg.fred_series == ("DGS10", "VIXCLS", "T10Y2Y")
    assert cfg.fred_lag_days == 1
    assert cfg.fred_history_days == 365
    assert cfg.normalize_window == 100
    assert cfg.normalize_min_periods == 30


def test_etl_config_context_defaults_to_none() -> None:
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
    )
    assert cfg.context is None


def test_path_config_context_path(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    assert paths.context_dir == tmp_path / "context"
    assert paths.context_path("insider", "AAPL") == (
        tmp_path / "context" / "insider" / "AAPL.parquet"
    )
    assert paths.context_path("fred", "DGS10") == (
        tmp_path / "context" / "fred" / "DGS10.parquet"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'ContextConfig'` (and the new tests erroring).

- [ ] **Step 3: Write the implementation**

In `config.py`, add the `ContextConfig` dataclass after `FeatureConfig`:

```python
@dataclass(frozen=True)
class ContextConfig:
    insider_net_window_days: int = 30
    insider_recency_cap_days: float = 252.0
    insider_lag_days: int = 1
    news_count_windows_days: tuple[int, ...] = (1, 5, 20)
    recommendation_lag_days: int = 0
    fred_series: tuple[str, ...] = ("DGS10", "VIXCLS", "T10Y2Y")
    fred_lag_days: int = 1
    fred_history_days: int = 365
    normalize_window: int = 100
    normalize_min_periods: int = 30
```

In `PathConfig`, add the context path helpers (after `dataset_dir`):

```python
    @property
    def context_dir(self) -> Path:
        return self.root / "context"

    def context_path(self, source: str, key: str) -> Path:
        return self.context_dir / source / f"{key}.parquet"
```

In `EtlConfig`, add the optional context field (after `paths`):

```python
    context: ContextConfig | None = None
```

Add `"ContextConfig"` to `__all__` (keep it sorted).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_config.py -v`
Expected: all config tests pass (the 4 original + 3 new).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/config.py services/api/tests/ml/test_ml_config.py
git commit -m "add: context config and context path conventions"
```

---

## Task 2: Context extraction — pure response→event-frame transforms

**Files:**
- Create: `services/api/app/ml/extract/context.py`
- Test: `services/api/tests/ml/test_ml_extract_context.py`

This task adds only the pure (no-network) helpers: the `available_utc` lag function and the four `*_to_frame` transforms that turn parsed source-client responses into canonical, sorted event frames. The async fetch loops come in Task 3 in the same file.

Canonical event-frame schemas (every `*_ts` column is tz-aware UTC):
- insider → columns `["available_ts", "change"]`
- news → column `["published_ts"]`
- recommendation → columns `["available_ts", "net_score"]`
- fred → columns `["available_ts", "value"]`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig
from app.ml.extract.context import (
    available_utc,
    fred_observations_to_frame,
    insider_events_to_frame,
    news_events_to_frame,
    recommendation_events_to_frame,
)
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransaction,
    FinnhubInsiderTransactionsResponse,
    FinnhubNewsItem,
    FinnhubRecommendation,
)
from app.services.source_clients.fred import FredObservation, FredSeriesObservations


def test_available_utc_lags_into_next_et_midnight() -> None:
    ts = available_utc(date(2026, 5, 15), 1)
    assert str(ts.tz) == "UTC"
    assert ts == pd.Timestamp("2026-05-16 00:00", tz="America/New_York").tz_convert("UTC")


def test_insider_events_to_frame_lags_and_sorts() -> None:
    response = FinnhubInsiderTransactionsResponse(
        symbol="AAPL",
        data=[
            FinnhubInsiderTransaction(
                name="A", share=1000, change=-500, filingDate="2026-05-15",
                transactionDate="2026-05-13", transactionCode="S", transactionPrice=195.5,
            ),
            FinnhubInsiderTransaction(
                name="B", share=200, change=200, filingDate="2026-05-10",
                transactionDate="2026-05-08", transactionCode="P",
            ),
        ],
    )
    frame = insider_events_to_frame(response, ContextConfig())
    assert list(frame.columns) == ["available_ts", "change"]
    assert frame["available_ts"].is_monotonic_increasing
    assert frame["change"].tolist() == [200, -500]
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-05-11 00:00", tz="America/New_York").tz_convert("UTC")
    )


def test_news_events_to_frame_collects_utc_published_ts() -> None:
    items = [
        FinnhubNewsItem(
            id=1, category="company", headline="h", source="s",
            url="https://example.com/1", published_at="2026-05-15T13:00:00Z",
        ),
        FinnhubNewsItem(
            id=2, category="company", headline="h2", source="s",
            url="https://example.com/2", published_at="2026-05-14T20:00:00Z",
        ),
    ]
    frame = news_events_to_frame(items)
    assert list(frame.columns) == ["published_ts"]
    assert frame["published_ts"].is_monotonic_increasing
    assert str(frame["published_ts"].dt.tz) == "UTC"


def test_news_events_to_frame_empty_keeps_schema() -> None:
    frame = news_events_to_frame([])
    assert list(frame.columns) == ["published_ts"]
    assert frame.empty


def test_recommendation_events_to_frame_next_month_and_net_score() -> None:
    items = [
        FinnhubRecommendation(
            symbol="AAPL", period="2026-05-01", buy=20, hold=5, sell=2,
            strongBuy=10, strongSell=1,
        )
    ]
    frame = recommendation_events_to_frame(items, ContextConfig())
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-06-01 00:00", tz="America/New_York").tz_convert("UTC")
    )
    assert abs(frame["net_score"].iloc[0] - (10 + 20 - 2 - 1) / 38) < 1e-9


def test_fred_observations_to_frame_skips_missing_and_lags() -> None:
    parsed = FredSeriesObservations(
        series_id="DGS10",
        observation_start="2026-05-01",
        observation_end="2026-05-05",
        count=3,
        observations=[
            FredObservation(date="2026-05-01", value="4.25",
                            realtime_start="2026-05-02", realtime_end="2026-12-31"),
            FredObservation(date="2026-05-02", value=".",
                            realtime_start="2026-05-03", realtime_end="2026-12-31"),
            FredObservation(date="2026-05-05", value="4.30",
                            realtime_start="2026-05-06", realtime_end="2026-12-31"),
        ],
    )
    frame = fred_observations_to_frame(parsed, ContextConfig())
    assert frame["value"].tolist() == [4.25, 4.30]
    assert frame["available_ts"].iloc[0] == (
        pd.Timestamp("2026-05-02 00:00", tz="America/New_York").tz_convert("UTC")
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ml.extract.context'`.

- [ ] **Step 3: Write the implementation (pure transforms only)**

```python
from __future__ import annotations

from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransactionsResponse,
    FinnhubNewsItem,
    FinnhubRecommendation,
)
from app.services.source_clients.fred import FredSeriesObservations

_ET = "America/New_York"
_UTC = "UTC"

_INSIDER_COLUMNS = ["available_ts", "change"]
_NEWS_COLUMNS = ["published_ts"]
_RECOMMENDATION_COLUMNS = ["available_ts", "net_score"]
_FRED_COLUMNS = ["available_ts", "value"]


def available_utc(day: date, lag_days: int) -> pd.Timestamp:
    """ET-midnight of ``day + lag_days`` expressed in UTC.

    A value dated ``day`` only becomes usable on bars at or after this instant,
    so with ``lag_days >= 1`` it can never appear on a bar during ``day`` itself
    (whose intraday publish time is unknown). This is the single point-in-time
    lag convention shared by insider filings, recommendations, and FRED.
    """
    return (pd.Timestamp(day, tz=_ET) + pd.Timedelta(days=lag_days)).tz_convert(_UTC)


def _to_utc(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(_UTC) if ts.tzinfo is None else ts.tz_convert(_UTC)


def _next_month_start(period: date) -> date:
    if period.month == 12:
        return date(period.year + 1, 1, 1)
    return date(period.year, period.month + 1, 1)


def insider_events_to_frame(
    response: FinnhubInsiderTransactionsResponse, config: ContextConfig
) -> pd.DataFrame:
    """Canonical insider-transaction events: signed share `change` at filing time."""
    rows = [
        {
            "available_ts": available_utc(txn.filing_date, config.insider_lag_days),
            "change": int(txn.change),
        }
        for txn in response.data
    ]
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "change": pd.Series([], dtype="int64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_INSIDER_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


def news_events_to_frame(items: list[FinnhubNewsItem]) -> pd.DataFrame:
    """Canonical news events: just the UTC publish timestamps (counts derived later)."""
    timestamps = [_to_utc(item.published_at) for item in items]
    series = pd.Series(timestamps, dtype="datetime64[ns, UTC]")
    frame = pd.DataFrame({"published_ts": series})
    return frame.sort_values("published_ts").reset_index(drop=True)


def recommendation_events_to_frame(
    items: list[FinnhubRecommendation], config: ContextConfig
) -> pd.DataFrame:
    """Canonical recommendation events: net bullishness, known from next month start."""
    rows: list[dict[str, object]] = []
    for rec in items:
        total = rec.strong_buy + rec.buy + rec.hold + rec.sell + rec.strong_sell
        net = (
            (rec.strong_buy + rec.buy - rec.sell - rec.strong_sell) / total
            if total > 0
            else 0.0
        )
        rows.append(
            {
                "available_ts": available_utc(
                    _next_month_start(rec.period), config.recommendation_lag_days
                ),
                "net_score": float(net),
            }
        )
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "net_score": pd.Series([], dtype="float64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_RECOMMENDATION_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


def fred_observations_to_frame(
    parsed: FredSeriesObservations, config: ContextConfig
) -> pd.DataFrame:
    """Canonical FRED events: numeric observations at observation_date + lag."""
    rows: list[dict[str, object]] = []
    for obs in parsed.observations:
        if obs.value is None:
            continue
        rows.append(
            {
                "available_ts": available_utc(obs.date, config.fred_lag_days),
                "value": float(obs.value),
            }
        )
    if not rows:
        return pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "value": pd.Series([], dtype="float64"),
            }
        )
    frame = pd.DataFrame(rows, columns=_FRED_COLUMNS)
    return frame.sort_values("available_ts").reset_index(drop=True)


__all__ = [
    "available_utc",
    "fred_observations_to_frame",
    "insider_events_to_frame",
    "news_events_to_frame",
    "recommendation_events_to_frame",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_context.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/extract/context.py services/api/tests/ml/test_ml_extract_context.py
git commit -m "add: point-in-time context event transforms"
```

---

## Task 3: Context extraction — async fetch + cache loops

**Files:**
- Modify: `services/api/app/ml/extract/context.py`
- Test: `services/api/tests/ml/test_ml_extract_context.py` (append)

Adds the async `pull_*` functions that call the existing source clients, convert with the Task-2 transforms, and write per-source parquet. News is fetched in month windows (reusing `month_windows` from `extract/bars.py`) so each Finnhub call stays small. FRED is pulled once per series over `[from_date - fred_history_days, to_date]`.

- [ ] **Step 1: Write the failing test (append)**

```python
import httpx
import pytest
import respx

from app.config import get_settings
from app.ml.config import PathConfig
from app.ml.extract.context import (
    pull_context_for_ticker,
    pull_fred,
)
from app.ml.storage import read_parquet


@pytest.fixture()
def _finnhub_fred_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test-key")
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    get_settings.cache_clear()


@respx.mock
async def test_pull_context_for_ticker_writes_three_sources(
    tmp_path: Path, _finnhub_fred_keys: None
) -> None:
    respx.get("https://finnhub.io/api/v1/stock/insider-transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "data": [
                    {
                        "name": "Tim Cook", "share": 1000, "change": -500,
                        "filingDate": "2026-05-15", "transactionDate": "2026-05-13",
                        "transactionCode": "S", "transactionPrice": 195.5,
                    }
                ],
            },
        )
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1, "category": "company", "headline": "h", "source": "s",
                    "url": "https://example.com/1", "datetime": 1778850000,
                }
            ],
        )
    )
    respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAPL", "period": "2026-05-01", "buy": 20, "hold": 5,
                    "sell": 2, "strongBuy": 10, "strongSell": 1,
                }
            ],
        )
    )

    paths = PathConfig(root=tmp_path)
    async with httpx.AsyncClient() as client:
        await pull_context_for_ticker(
            client=client,
            ticker="AAPL",
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 20),
            config=ContextConfig(),
            paths=paths,
        )

    insider = read_parquet(paths.context_path("insider", "AAPL"))
    news = read_parquet(paths.context_path("news", "AAPL"))
    recommendation = read_parquet(paths.context_path("recommendation", "AAPL"))
    assert insider["change"].tolist() == [-500]
    assert list(news.columns) == ["published_ts"]
    assert len(news) == 1
    assert abs(recommendation["net_score"].iloc[0] - (10 + 20 - 2 - 1) / 38) < 1e-9


@respx.mock
async def test_pull_fred_writes_one_parquet_per_series(
    tmp_path: Path, _finnhub_fred_keys: None
) -> None:
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(
            200,
            json={
                "observation_start": "2025-05-01",
                "observation_end": "2026-05-20",
                "count": 2,
                "observations": [
                    {"date": "2026-05-01", "value": "4.25",
                     "realtime_start": "2026-05-02", "realtime_end": "2026-12-31"},
                    {"date": "2026-05-02", "value": ".",
                     "realtime_start": "2026-05-03", "realtime_end": "2026-12-31"},
                ],
            },
        )
    )

    paths = PathConfig(root=tmp_path)
    config = ContextConfig(fred_series=("DGS10",))
    async with httpx.AsyncClient() as client:
        written = await pull_fred(
            client=client,
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 20),
            config=config,
            paths=paths,
        )

    assert written == [paths.context_path("fred", "DGS10")]
    frame = read_parquet(paths.context_path("fred", "DGS10"))
    assert frame["value"].tolist() == [4.25]
```

(Note: the new test references `ContextConfig` and `date`, already imported at the top of this file in Task 2.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_context.py -k "pull" -v`
Expected: FAIL with `ImportError: cannot import name 'pull_context_for_ticker'`.

- [ ] **Step 3: Add the async fetch loops to `context.py`**

Add these imports at the top of `context.py`:

```python
from datetime import timedelta
from pathlib import Path

import httpx

from app.ml.extract.bars import month_windows
from app.ml.storage import write_parquet
from app.services.source_clients.finnhub import (
    fetch_finnhub_company_news,
    fetch_finnhub_insider_transactions,
    fetch_finnhub_recommendation,
)
from app.services.source_clients.fred import fetch_series_observations
```

(Keep the existing model imports; add the `fetch_*` function imports alongside them.)

Add the functions:

```python
async def pull_insider(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: Path | object = None,  # placeholder; replaced below
) -> Path:  # pragma: no cover - signature replaced below
    raise NotImplementedError
```

Replace the placeholder above with the real implementations (the `pull_*` functions take a `PathConfig`; import it):

```python
from app.ml.config import ContextConfig, PathConfig
```

```python
async def pull_insider(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> Path:
    response, _ = await fetch_finnhub_insider_transactions(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    frame = insider_events_to_frame(response, config)
    path = paths.context_path("insider", ticker)
    write_parquet(frame, path)
    return path


async def pull_news(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    paths: PathConfig,
) -> Path:
    frames: list[pd.DataFrame] = []
    for window_start, window_end in month_windows(from_date, to_date):
        items, _ = await fetch_finnhub_company_news(
            client=client, symbol=ticker, from_date=window_start, to_date=window_end
        )
        frames.append(news_events_to_frame(items))
    combined = (
        pd.concat(frames, ignore_index=True) if frames else news_events_to_frame([])
    )
    combined = combined.sort_values("published_ts").reset_index(drop=True)
    path = paths.context_path("news", ticker)
    write_parquet(combined, path)
    return path


async def pull_recommendation(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    config: ContextConfig,
    paths: PathConfig,
) -> Path:
    items, _ = await fetch_finnhub_recommendation(client=client, symbol=ticker)
    frame = recommendation_events_to_frame(items, config)
    path = paths.context_path("recommendation", ticker)
    write_parquet(frame, path)
    return path


async def pull_fred(
    *,
    client: httpx.AsyncClient,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> list[Path]:
    observation_start = from_date - timedelta(days=config.fred_history_days)
    written: list[Path] = []
    for series_id in config.fred_series:
        parsed, _ = await fetch_series_observations(
            client=client,
            series_id=series_id,
            observation_start=observation_start,
            observation_end=to_date,
        )
        frame = fred_observations_to_frame(parsed, config)
        path = paths.context_path("fred", series_id)
        write_parquet(frame, path)
        written.append(path)
    return written


async def pull_context_for_ticker(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    from_date: date,
    to_date: date,
    config: ContextConfig,
    paths: PathConfig,
) -> None:
    await pull_insider(
        client=client, ticker=ticker, from_date=from_date, to_date=to_date,
        config=config, paths=paths,
    )
    await pull_news(
        client=client, ticker=ticker, from_date=from_date, to_date=to_date, paths=paths
    )
    await pull_recommendation(
        client=client, ticker=ticker, config=config, paths=paths
    )
```

**Important:** remove the `NotImplementedError` placeholder `pull_insider` stub shown earlier in this step — it exists only to anchor the edit; the real `pull_insider` above is the keeper. Extend `__all__` to include the five new names:

```python
__all__ = [
    "available_utc",
    "fred_observations_to_frame",
    "insider_events_to_frame",
    "news_events_to_frame",
    "pull_context_for_ticker",
    "pull_fred",
    "pull_insider",
    "pull_news",
    "pull_recommendation",
    "recommendation_events_to_frame",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_extract_context.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/extract/context.py services/api/tests/ml/test_ml_extract_context.py
git commit -m "add: async context source fetch and cache loops"
```

---

## Task 4: Context join — as-of features, columns, bundle loader (crown jewel)

**Files:**
- Create: `services/api/app/ml/features/context_join.py`
- Test: `services/api/tests/ml/test_ml_features_context_join.py`

All joins are vectorized integer-nanosecond `searchsorted` over the bar grid — strictly backward (`side="right"`), so an event whose timestamp is `> bar_t` is never visible at bar `t`. News uses rolling counts in trailing wall-clock windows ending at `t`; insider/recommendation/FRED forward-fill the last event at or before `t`.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig, PathConfig
from app.ml.features.context_join import (
    ContextBundle,
    build_context_features,
    context_feature_columns,
    context_normalize_columns,
    load_context_bundle,
)
from app.ml.storage import write_parquet


def _empty_insider() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
            "change": pd.Series([], dtype="int64"),
        }
    )


def _empty_news() -> pd.DataFrame:
    return pd.DataFrame({"published_ts": pd.Series([], dtype="datetime64[ns, UTC]")})


def _empty_rec() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
            "net_score": pd.Series([], dtype="float64"),
        }
    )


def test_context_feature_columns_order() -> None:
    cols = context_feature_columns(ContextConfig())
    assert cols == [
        "insider_net_30d",
        "insider_days_since",
        "news_count_1d",
        "news_count_5d",
        "news_count_20d",
        "rec_net_score",
        "fred_DGS10",
        "fred_DGS10_chg",
        "fred_VIXCLS",
        "fred_VIXCLS_chg",
        "fred_T10Y2Y",
        "fred_T10Y2Y_chg",
    ]


def test_context_normalize_columns_subset() -> None:
    cols = context_normalize_columns(ContextConfig())
    assert cols == [
        "insider_net_30d",
        "news_count_1d",
        "news_count_5d",
        "news_count_20d",
        "fred_DGS10",
        "fred_VIXCLS",
        "fred_T10Y2Y",
    ]


def test_event_after_bar_never_appears() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-10T14:30:00Z"], tz="UTC")
    insider = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(["2025-03-11T00:00:00Z"], utc=True),
            "change": [-1000],
        }
    )
    news = pd.DataFrame(
        {"published_ts": pd.to_datetime(["2025-03-11T10:00:00Z"], utc=True)}
    )
    rec = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(["2025-03-12T00:00:00Z"], utc=True),
            "net_score": [0.9],
        }
    )
    fred = {
        "DGS10": pd.DataFrame(
            {
                "available_ts": pd.to_datetime(["2025-03-12T00:00:00Z"], utc=True),
                "value": [4.5],
            }
        )
    }
    bundle = ContextBundle(insider=insider, news=news, recommendation=rec, fred=fred)
    cfg = ContextConfig(fred_series=("DGS10",))
    feats = build_context_features(bar_index, bundle, cfg)
    assert feats.loc[bar_index[0], "insider_net_30d"] == 0.0
    assert feats.loc[bar_index[0], "insider_days_since"] == cfg.insider_recency_cap_days
    assert feats.loc[bar_index[0], "news_count_1d"] == 0.0
    assert feats.loc[bar_index[0], "rec_net_score"] == 0.0
    assert pd.isna(feats.loc[bar_index[0], "fred_DGS10"])


def test_news_counts_trailing_windows() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-10T14:30:00Z"], tz="UTC")
    news = pd.DataFrame(
        {
            "published_ts": pd.to_datetime(
                ["2025-03-10T10:00:00Z", "2025-03-09T10:00:00Z", "2025-03-01T10:00:00Z"],
                utc=True,
            )
        }
    )
    bundle = ContextBundle(
        insider=_empty_insider(), news=news, recommendation=_empty_rec(), fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "news_count_1d"] == 1.0
    assert feats.loc[bar_index[0], "news_count_5d"] == 2.0
    assert feats.loc[bar_index[0], "news_count_20d"] == 3.0


def test_insider_net_and_recency() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    insider = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(
                ["2025-03-10T00:00:00Z", "2025-03-18T00:00:00Z"], utc=True
            ),
            "change": [1000, -400],
        }
    )
    bundle = ContextBundle(
        insider=insider, news=_empty_news(), recommendation=_empty_rec(), fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "insider_net_30d"] == 600.0
    assert abs(feats.loc[bar_index[0], "insider_days_since"] - (2 + 14.5 / 24)) < 1e-6


def test_recommendation_forward_fill() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    rec = pd.DataFrame(
        {
            "available_ts": pd.to_datetime(
                ["2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z"], utc=True
            ),
            "net_score": [0.2, 0.5],
        }
    )
    bundle = ContextBundle(
        insider=_empty_insider(), news=_empty_news(), recommendation=rec, fred={}
    )
    feats = build_context_features(bar_index, bundle, ContextConfig())
    assert feats.loc[bar_index[0], "rec_net_score"] == 0.5


def test_fred_level_and_change_forward_fill() -> None:
    bar_index = pd.DatetimeIndex(["2025-03-20T14:30:00Z"], tz="UTC")
    fred = {
        "DGS10": pd.DataFrame(
            {
                "available_ts": pd.to_datetime(
                    ["2025-03-18T00:00:00Z", "2025-03-19T00:00:00Z"], utc=True
                ),
                "value": [4.20, 4.30],
            }
        )
    }
    bundle = ContextBundle(
        insider=_empty_insider(), news=_empty_news(), recommendation=_empty_rec(),
        fred=fred,
    )
    feats = build_context_features(bar_index, bundle, ContextConfig(fred_series=("DGS10",)))
    assert abs(feats.loc[bar_index[0], "fred_DGS10"] - 4.30) < 1e-9
    assert abs(feats.loc[bar_index[0], "fred_DGS10_chg"] - 0.10) < 1e-9


def test_load_context_bundle_roundtrip(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    write_parquet(
        pd.DataFrame(
            {
                "available_ts": pd.to_datetime(["2025-03-10T00:00:00Z"], utc=True),
                "change": [100],
            }
        ),
        paths.context_path("insider", "AAPL"),
    )
    bundle = load_context_bundle("AAPL", ContextConfig(fred_series=()), paths)
    assert bundle.insider["change"].tolist() == [100]
    assert list(bundle.news.columns) == ["published_ts"]
    assert bundle.news.empty
    assert bundle.fred == {}
```

(`Path` is needed for the typed `tmp_path`; add `from pathlib import Path` to this test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_context_join.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ml.features.context_join'`.

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.ml.config import ContextConfig, PathConfig
from app.ml.storage import read_parquet

_NS_PER_DAY = 86_400_000_000_000

_INSIDER_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "change": "int64"}
_NEWS_SCHEMA = {"published_ts": "datetime64[ns, UTC]"}
_RECOMMENDATION_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "net_score": "float64"}
_FRED_SCHEMA = {"available_ts": "datetime64[ns, UTC]", "value": "float64"}


@dataclass(frozen=True)
class ContextBundle:
    insider: pd.DataFrame
    news: pd.DataFrame
    recommendation: pd.DataFrame
    fred: dict[str, pd.DataFrame] = field(default_factory=dict)


def context_feature_columns(config: ContextConfig) -> list[str]:
    """Ordered context feature column names (must match build_context_features)."""
    cols = [f"insider_net_{config.insider_net_window_days}d", "insider_days_since"]
    cols += [f"news_count_{window}d" for window in config.news_count_windows_days]
    cols += ["rec_net_score"]
    for series_id in config.fred_series:
        cols += [f"fred_{series_id}", f"fred_{series_id}_chg"]
    return cols


def context_normalize_columns(config: ContextConfig) -> list[str]:
    """Context columns that get causal per-ticker z-scoring (scale-bearing ones).

    Recency (bounded by a cap), recommendation net-score (bounded in [-1, 1]), and
    FRED first-differences are left raw; counts, signed insider flow, and FRED
    levels vary by scale and are normalized.
    """
    cols = [f"insider_net_{config.insider_net_window_days}d"]
    cols += [f"news_count_{window}d" for window in config.news_count_windows_days]
    cols += [f"fred_{series_id}" for series_id in config.fred_series]
    return cols


def _insider_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    frame = bundle.insider.sort_values("available_ts")
    if frame.empty:
        event_ns = np.empty(0, dtype="int64")
        change = np.empty(0, dtype="float64")
    else:
        event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
        change = frame["change"].to_numpy(dtype="float64")

    window_ns = config.insider_net_window_days * _NS_PER_DAY
    prefix = np.concatenate([[0.0], np.cumsum(change)])
    upper = np.searchsorted(event_ns, bar_ns, side="right")
    lower = np.searchsorted(event_ns, bar_ns - window_ns, side="right")
    net = prefix[upper] - prefix[lower]

    last = upper - 1
    recency = np.full(len(bar_index), config.insider_recency_cap_days, dtype="float64")
    has_prior = last >= 0
    recency[has_prior] = np.minimum(
        (bar_ns[has_prior] - event_ns[last[has_prior]]) / _NS_PER_DAY,
        config.insider_recency_cap_days,
    )
    return pd.DataFrame(
        {
            f"insider_net_{config.insider_net_window_days}d": net,
            "insider_days_since": recency,
        },
        index=bar_index,
    )


def _news_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    if bundle.news.empty:
        event_ns = np.empty(0, dtype="int64")
    else:
        event_ns = np.sort(pd.DatetimeIndex(bundle.news["published_ts"]).asi8)
    upper = np.searchsorted(event_ns, bar_ns, side="right")
    data: dict[str, object] = {}
    for window in config.news_count_windows_days:
        lower = np.searchsorted(event_ns, bar_ns - window * _NS_PER_DAY, side="right")
        data[f"news_count_{window}d"] = (upper - lower).astype("float64")
    return pd.DataFrame(data, index=bar_index)


def _recommendation_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    out = np.zeros(len(bar_index), dtype="float64")
    frame = bundle.recommendation.sort_values("available_ts")
    if not frame.empty:
        event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
        score = frame["net_score"].to_numpy(dtype="float64")
        last = np.searchsorted(event_ns, bar_ns, side="right") - 1
        has_prior = last >= 0
        out[has_prior] = score[last[has_prior]]
    return pd.DataFrame({"rec_net_score": out}, index=bar_index)


def _fred_features(
    bundle: ContextBundle, bar_index: pd.DatetimeIndex, config: ContextConfig
) -> pd.DataFrame:
    bar_ns = bar_index.asi8
    data: dict[str, object] = {}
    for series_id in config.fred_series:
        level = np.full(len(bar_index), np.nan, dtype="float64")
        change = np.full(len(bar_index), np.nan, dtype="float64")
        frame = bundle.fred.get(series_id)
        if frame is not None and not frame.empty:
            frame = frame.sort_values("available_ts")
            event_ns = pd.DatetimeIndex(frame["available_ts"]).asi8
            value = frame["value"].to_numpy(dtype="float64")
            last = np.searchsorted(event_ns, bar_ns, side="right") - 1
            has_prior = last >= 0
            level[has_prior] = value[last[has_prior]]
            prev = last - 1
            has_prev = has_prior & (prev >= 0)
            change[has_prev] = value[last[has_prev]] - value[prev[has_prev]]
            change[has_prior & (prev < 0)] = 0.0
        data[f"fred_{series_id}"] = level
        data[f"fred_{series_id}_chg"] = change
    return pd.DataFrame(data, index=bar_index)


def build_context_features(
    bar_index: pd.DatetimeIndex, bundle: ContextBundle, config: ContextConfig
) -> pd.DataFrame:
    """Context features aligned to `bar_index`, strictly causal (no future events)."""
    parts = [
        _insider_features(bundle, bar_index, config),
        _news_features(bundle, bar_index, config),
        _recommendation_features(bundle, bar_index, config),
        _fred_features(bundle, bar_index, config),
    ]
    out = pd.concat(parts, axis=1)
    return out[context_feature_columns(config)]


def _read_or_empty(path: Path, schema: dict[str, str]) -> pd.DataFrame:
    if path.exists():
        return read_parquet(path)
    return pd.DataFrame({name: pd.Series([], dtype=dtype) for name, dtype in schema.items()})


def load_context_bundle(
    ticker: str, config: ContextConfig, paths: PathConfig
) -> ContextBundle:
    """Load cached per-source context parquet into a ContextBundle for one ticker."""
    insider = _read_or_empty(paths.context_path("insider", ticker), _INSIDER_SCHEMA)
    news = _read_or_empty(paths.context_path("news", ticker), _NEWS_SCHEMA)
    recommendation = _read_or_empty(
        paths.context_path("recommendation", ticker), _RECOMMENDATION_SCHEMA
    )
    fred = {
        series_id: _read_or_empty(paths.context_path("fred", series_id), _FRED_SCHEMA)
        for series_id in config.fred_series
    }
    return ContextBundle(
        insider=insider, news=news, recommendation=recommendation, fred=fred
    )


__all__ = [
    "ContextBundle",
    "build_context_features",
    "context_feature_columns",
    "context_normalize_columns",
    "load_context_bundle",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_features_context_join.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/features/context_join.py services/api/tests/ml/test_ml_features_context_join.py
git commit -m "add: point-in-time context join and bundle loader"
```

---

## Task 5: Assembly integration — append normalized context columns

**Files:**
- Modify: `services/api/app/ml/assemble.py`
- Test: `services/api/tests/ml/test_ml_assemble.py` (append)

Context is opt-in. When `config.context is None`, `build_ticker_dataset` behaves exactly as Plan A (existing tests untouched). When `config.context` is set, the caller **must** pass a `ContextBundle` (else `ValueError` — never silently skip), and the normalized context columns are appended, included in the NaN-drop gate, and recorded in `feature_spec.json` / `manifest.json`.

- [ ] **Step 1: Write the failing test (append)**

```python
from app.ml.config import ContextConfig
from app.ml.features.context_join import (
    ContextBundle,
    context_feature_columns,
)


def _context_bundle(bars: pd.DataFrame) -> ContextBundle:
    start = bars.index[0]
    insider = pd.DataFrame(
        {
            "available_ts": [start - pd.Timedelta(days=2)],
            "change": [1000],
        }
    )
    news = pd.DataFrame(
        {"published_ts": [start - pd.Timedelta(hours=3), start + pd.Timedelta(hours=1)]}
    )
    recommendation = pd.DataFrame(
        {"available_ts": [start - pd.Timedelta(days=5)], "net_score": [0.4]}
    )
    fred = {
        series_id: pd.DataFrame(
            {
                "available_ts": [
                    start - pd.Timedelta(days=3),
                    start - pd.Timedelta(days=2),
                ],
                "value": [4.2, 4.3],
            }
        )
        for series_id in ("DGS10", "VIXCLS", "T10Y2Y")
    }
    return ContextBundle(
        insider=insider, news=news, recommendation=recommendation, fred=fred
    )


def test_build_ticker_dataset_appends_context_columns() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    frame = build_ticker_dataset("AAPL", bars, cfg, context=_context_bundle(bars))
    for col in context_feature_columns(ContextConfig()):
        assert col in frame.columns
        assert frame[col].notna().all()
    assert frame["barrier_label"].notna().all()


def test_build_ticker_dataset_context_is_deterministic() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    bundle = _context_bundle(bars)
    a = build_ticker_dataset("AAPL", bars, cfg, context=bundle)
    b = build_ticker_dataset("AAPL", bars, cfg, context=bundle)
    pd.testing.assert_frame_equal(a, b)


def test_build_ticker_dataset_without_context_has_no_context_columns() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
    )
    frame = build_ticker_dataset("AAPL", bars, cfg)
    for col in context_feature_columns(ContextConfig()):
        assert col not in frame.columns


def test_build_ticker_dataset_context_config_without_bundle_raises() -> None:
    bars = _bars(220)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    with pytest.raises(ValueError, match="context"):
        build_ticker_dataset("AAPL", bars, cfg)
```

(Add `import pytest` to the top of `test_ml_assemble.py` if it is not already imported.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_assemble.py -k context -v`
Expected: FAIL — `build_ticker_dataset()` got an unexpected keyword argument `context` (and `ValueError` not raised).

- [ ] **Step 3: Modify `assemble.py`**

Add imports (after the existing `from app.ml.config ...` line, and a new import block):

```python
from app.ml.config import ContextConfig, EtlConfig, FeatureConfig
from app.ml.features.context_join import (
    ContextBundle,
    build_context_features,
    context_feature_columns,
    context_normalize_columns,
)
```

(Replace the existing `from app.ml.config import EtlConfig, FeatureConfig` line with the one above that also imports `ContextConfig`.)

Add a module-level helper that returns the full ordered feature list (spine + context when enabled), after `feature_columns`:

```python
def all_feature_columns(config: EtlConfig) -> list[str]:
    """Spine feature columns, plus context columns when context is enabled."""
    cols = feature_columns(config.features)
    if config.context is not None:
        cols = cols + context_feature_columns(config.context)
    return cols
```

Replace the body of `build_ticker_dataset` with a context-aware version (note the new `context` parameter and the `all_feature_columns` usage):

```python
def build_ticker_dataset(
    ticker: str,
    bars: pd.DataFrame,
    config: EtlConfig,
    context: ContextBundle | None = None,
) -> pd.DataFrame:
    """Build a labeled, feature-complete dataset for one ticker (RTH bars only).

    When `config.context` is set, `context` must be supplied; its normalized
    columns are appended to the spine features and included in the NaN-drop gate.
    """
    if config.context is not None and context is None:
        raise ValueError(
            "config.context is set but no context bundle was provided to "
            "build_ticker_dataset"
        )

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

    if config.context is not None and context is not None:
        context_features = build_context_features(rth.index, context, config.context)
        context_features = normalize_columns(
            context_features,
            context_normalize_columns(config.context),
            window=config.context.normalize_window,
            min_periods=config.context.normalize_min_periods,
        )
        features = pd.concat([features, context_features], axis=1)

    combined = pd.concat([features, labels], axis=1)
    combined.insert(0, "ticker", ticker)
    model_columns = all_feature_columns(config)
    combined = combined[model_columns + _META_COLUMNS]

    feature_only = combined[model_columns]
    combined = combined[
        feature_only.notna().all(axis=1) & combined["barrier_label"].notna()
    ]
    combined = combined.reset_index().rename(columns={"timestamp": "entry_ts"})
    combined["session_date"] = combined["entry_ts"].dt.tz_convert(
        "America/New_York"
    ).dt.date.astype(str)
    return combined.sort_values(["ticker", "entry_ts"]).reset_index(drop=True)
```

Update `assemble_dataset` to use `all_feature_columns(config)` and to record context in the spec and manifest. Replace the dataset-construction line, the spec block, and add a manifest context block:

```python
    frames = [frame for frame in per_ticker.values() if not frame.empty]
    model_columns = all_feature_columns(config)
    dataset = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=model_columns + _META_COLUMNS)
    )
```

In the `manifest` dict, after `"label_balance"`, add the context block:

```python
    if config.context is not None:
        manifest["context"] = {
            "fred_series": list(config.context.fred_series),
            "news_count_windows_days": list(config.context.news_count_windows_days),
            "insider_net_window_days": config.context.insider_net_window_days,
        }
```

Replace the `spec` dict so `features` and `normalized` include context when enabled:

```python
    normalized = list(_NORMALIZE_COLUMNS)
    if config.context is not None:
        normalized += context_normalize_columns(config.context)
    spec: dict[str, Any] = {
        "features": model_columns,
        "normalized": normalized,
        "label": "barrier_label",
    }
```

Add `"all_feature_columns"` to `__all__` (keep sorted).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_assemble.py -v`
Expected: all assemble tests pass (the 4 original + 4 new).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/assemble.py services/api/tests/ml/test_ml_assemble.py
git commit -m "add: optional context columns in dataset assembly"
```

---

## Task 6: CLI — pull-context command + build-dataset --with-context

**Files:**
- Modify: `services/api/app/ml/cli.py`
- Test: `services/api/tests/ml/test_ml_cli.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
import httpx
import respx

from app.config import get_settings
from app.ml.config import ContextConfig
from app.ml.features.context_join import context_feature_columns
from app.ml.storage import read_parquet


def _write_context(paths: PathConfig, ticker: str) -> None:
    start = pd.Timestamp("2025-01-02T14:30:00Z")
    write_parquet(
        pd.DataFrame(
            {"available_ts": [start - pd.Timedelta(days=2)], "change": [1000]}
        ),
        paths.context_path("insider", ticker),
    )
    write_parquet(
        pd.DataFrame({"published_ts": [start - pd.Timedelta(hours=2)]}),
        paths.context_path("news", ticker),
    )
    write_parquet(
        pd.DataFrame(
            {"available_ts": [start - pd.Timedelta(days=5)], "net_score": [0.3]}
        ),
        paths.context_path("recommendation", ticker),
    )
    for series_id in ContextConfig().fred_series:
        write_parquet(
            pd.DataFrame(
                {
                    "available_ts": [
                        start - pd.Timedelta(days=3),
                        start - pd.Timedelta(days=2),
                    ],
                    "value": [4.2, 4.3],
                }
            ),
            paths.context_path("fred", series_id),
        )


def test_build_dataset_with_context_includes_context_columns(tmp_path: Path) -> None:
    paths = PathConfig(root=tmp_path)
    _write_raw(paths, "AAPL")
    _write_context(paths, "AAPL")
    result = runner.invoke(
        app,
        [
            "build-dataset",
            "--ticker", "AAPL",
            "--from-date", "2025-01-02",
            "--to-date", "2025-01-03",
            "--run-id", "ctxrun",
            "--root", str(tmp_path),
            "--with-context",
        ],
    )
    assert result.exit_code == 0, result.output
    dataset = read_parquet(paths.dataset_dir("ctxrun") / "dataset.parquet")
    for col in context_feature_columns(ContextConfig()):
        assert col in dataset.columns
    assert len(dataset) > 0


@respx.mock
def test_pull_context_writes_source_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test-key")
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    get_settings.cache_clear()

    respx.get("https://finnhub.io/api/v1/stock/insider-transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "data": [
                    {
                        "name": "Tim Cook", "share": 1000, "change": -500,
                        "filingDate": "2026-05-15", "transactionDate": "2026-05-13",
                        "transactionCode": "S",
                    }
                ],
            },
        )
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(
            200,
            json={
                "observation_start": "2025-05-01",
                "observation_end": "2026-05-20",
                "count": 1,
                "observations": [
                    {"date": "2026-05-01", "value": "4.25",
                     "realtime_start": "2026-05-02", "realtime_end": "2026-12-31"}
                ],
            },
        )
    )

    paths = PathConfig(root=tmp_path)
    result = runner.invoke(
        app,
        [
            "pull-context",
            "--ticker", "AAPL",
            "--from-date", "2026-05-01",
            "--to-date", "2026-05-20",
            "--root", str(tmp_path),
            "--fred-series", "DGS10",
        ],
    )
    assert result.exit_code == 0, result.output
    assert paths.context_path("insider", "AAPL").exists()
    assert paths.context_path("news", "AAPL").exists()
    assert paths.context_path("recommendation", "AAPL").exists()
    assert paths.context_path("fred", "DGS10").exists()
```

(`pytest` and `pd` are already imported at the top of `test_ml_cli.py` from Plan A; `httpx`, `respx`, and the new `app.*` symbols are added here.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && uv run pytest tests/ml/test_ml_cli.py -v`
Expected: FAIL — `build-dataset` has no `--with-context` option / `pull-context` command does not exist.

- [ ] **Step 3: Modify `cli.py`**

Add imports:

```python
from app.ml.config import ContextConfig, EtlConfig, PathConfig
from app.ml.extract.context import pull_context_for_ticker, pull_fred
from app.ml.features.context_join import ContextBundle, load_context_bundle
```

(Replace the existing `from app.ml.config import EtlConfig, PathConfig` line with the `ContextConfig`-inclusive one above.)

Extend `_config` to accept an optional context config:

```python
def _config(
    tickers: tuple[str, ...],
    from_date: date,
    to_date: date,
    root: Path,
    context: ContextConfig | None = None,
) -> EtlConfig:
    return EtlConfig(
        tickers=tickers,
        from_date=from_date,
        to_date=to_date,
        paths=PathConfig(root=root),
        context=context,
    )
```

Add a `--with-context` flag to `build_dataset` and wire in the bundle loader. Replace the `build_dataset` function with:

```python
@app.command("build-dataset")
def build_dataset(
    run_id: str = typer.Option(..., "--run-id"),
    ticker: list[str] | None = typer.Option(None, "--ticker"),  # noqa: B008
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),  # noqa: B008
    with_context: bool = typer.Option(False, "--with-context"),
) -> None:
    """Build a labeled dataset from already-cached raw bars (and optional context)."""
    universe = resolve_universe(ticker or None)
    context_config = ContextConfig() if with_context else None
    config = _config(
        universe,
        date.fromisoformat(from_date),
        date.fromisoformat(to_date),
        root,
        context=context_config,
    )
    per_ticker: dict[str, object] = {}
    for symbol in universe:
        raw_path = config.paths.raw_bars_path(symbol)
        if not raw_path.exists():
            logger.warning("missing_raw_bars", ticker=symbol)
            continue
        bars = read_parquet(raw_path)
        bundle: ContextBundle | None = (
            load_context_bundle(symbol, context_config, config.paths)
            if context_config is not None
            else None
        )
        per_ticker[symbol] = build_ticker_dataset(symbol, bars, config, context=bundle)
    out_dir = assemble_dataset(run_id, per_ticker, config)
    typer.echo(str(out_dir))
```

Add the `pull-context` command (after `build_dataset`):

```python
@app.command("pull-context")
def pull_context(
    ticker: list[str] | None = typer.Option(None, "--ticker"),  # noqa: B008
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),  # noqa: B008
    fred_series: list[str] | None = typer.Option(None, "--fred-series"),  # noqa: B008
) -> None:
    """Fetch and cache point-in-time context sources for the universe to parquet."""
    universe = resolve_universe(ticker or None)
    paths = PathConfig(root=root)
    config = (
        ContextConfig(fred_series=tuple(fred_series))
        if fred_series
        else ContextConfig()
    )
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)

    async def _run() -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await pull_fred(
                client=client, from_date=start, to_date=end, config=config, paths=paths
            )
            for symbol in universe:
                await pull_context_for_ticker(
                    client=client,
                    ticker=symbol,
                    from_date=start,
                    to_date=end,
                    config=config,
                    paths=paths,
                )
                logger.info("pulled_context", ticker=symbol)

    asyncio.run(_run())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_cli.py -v`
Expected: all CLI tests pass (the 1 original + 2 new).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/ml/cli.py services/api/tests/ml/test_ml_cli.py
git commit -m "add: pull-context cli and build-dataset context flag"
```

---

## Task 7: Integration — context leakage invariant + determinism

**Files:**
- Test: `services/api/tests/ml/test_ml_integration.py` (append)

No new production code; asserts the spec §9 leakage invariants and §10 determinism with context enabled, and confirms the crown-jewel guard still holds end-to-end with context columns present.

- [ ] **Step 1: Write the failing test (append)**

```python
from app.ml.config import ContextConfig
from app.ml.features.context_join import ContextBundle, context_feature_columns


def _context_bundle(bars: pd.DataFrame) -> ContextBundle:
    start = bars.index[0]
    insider = pd.DataFrame(
        {"available_ts": [start - pd.Timedelta(days=2)], "change": [1000]}
    )
    news = pd.DataFrame({"published_ts": [start - pd.Timedelta(hours=2)]})
    recommendation = pd.DataFrame(
        {"available_ts": [start - pd.Timedelta(days=5)], "net_score": [0.4]}
    )
    fred = {
        series_id: pd.DataFrame(
            {
                "available_ts": [
                    start - pd.Timedelta(days=3),
                    start - pd.Timedelta(days=2),
                ],
                "value": [4.2, 4.3],
            }
        )
        for series_id in ContextConfig().fred_series
    }
    return ContextBundle(
        insider=insider, news=news, recommendation=recommendation, fred=fred
    )


def test_future_insider_event_never_appears_in_earlier_bar() -> None:
    bars = _bars(220, 7)
    start = bars.index[0]
    bundle = ContextBundle(
        insider=pd.DataFrame(
            {"available_ts": [bars.index[-1] + pd.Timedelta(days=1)], "change": [9999]}
        ),
        news=pd.DataFrame({"published_ts": pd.Series([], dtype="datetime64[ns, UTC]")}),
        recommendation=pd.DataFrame(
            {
                "available_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "net_score": pd.Series([], dtype="float64"),
            }
        ),
        fred={},
    )
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=start.date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(fred_series=()),
    )
    ds = build_ticker_dataset("AAPL", bars, cfg, context=bundle)
    assert (ds["insider_net_30d"] == 0.0).all()
    assert (ds["insider_days_since"] == ContextConfig().insider_recency_cap_days).all()


def test_modifying_future_bars_never_changes_past_features_with_context() -> None:
    bars = _bars(220, 8)
    cfg = EtlConfig(
        tickers=("AAPL",),
        from_date=bars.index[0].date(),
        to_date=bars.index[-1].date(),
        context=ContextConfig(),
    )
    bundle = _context_bundle(bars)
    base = build_ticker_dataset("AAPL", bars, cfg, context=bundle)

    tampered = bars.copy()
    tampered.iloc[180:, tampered.columns.get_loc("close")] *= 1.5
    tampered.iloc[180:, tampered.columns.get_loc("high")] *= 1.5
    after = build_ticker_dataset("AAPL", tampered, cfg, context=bundle)

    cutoff = base["entry_ts"].iloc[100]
    cols = feature_columns(FeatureConfig()) + context_feature_columns(ContextConfig())
    base_head = base[base["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    after_head = after[after["entry_ts"] <= cutoff][["entry_ts", *cols]].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_head, after_head)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd services/api && uv run pytest tests/ml/test_ml_integration.py -v`
Expected: PASS (production code already exists). If `test_modifying_future_bars_never_changes_past_features_with_context` fails, a context feature is reading future events or a spine feature is leaking — fix the offending feature, never the test.

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
git commit -m "add: context leakage and determinism integration tests"
```

---

## Self-review (completed against spec)

- **Spec §5.3 context extraction** → Task 2 (transforms) + Task 3 (async fetch/cache to per-source parquet under `data/ml/context/`).
- **Spec §6 Context family** (insider recency + net intensity; trailing news counts in multiple windows; recommendation trend; FRED levels and changes) → Task 4 `build_context_features` (`insider_net_Nd`, `insider_days_since`, `news_count_{1,5,20}d`, `rec_net_score`, `fred_<series>` + `fred_<series>_chg`).
- **Spec §6 normalization** (per-ticker causal rolling, scale-free features skipped) → Task 5 normalizes the scale-bearing subset (`context_normalize_columns`) and leaves recency / net-score / first-differences raw.
- **Spec §9 leakage invariants** → §9.1/§9.2 backward as-of from real event time (Task 4 `searchsorted(side="right")` + the +lag `available_utc` convention); §9.3 causal normalization (Task 5 reuses `causal_zscore`); §9.4 no future imputation (no-event defaults are constants, never future values). Verified by Task 4 `test_event_after_bar_never_appears` and Task 7 `test_future_insider_event_never_appears_in_earlier_bar` + the tamper test with context columns.
- **Spec §10 tests** → context-join correctness/leakage (Task 4), assembly + determinism (Task 5), end-to-end leakage/determinism (Task 7).
- **Spec §11 CLI** → `pull-context` and `build-dataset --with-context` (Task 6).
- **Spec §12 excluded snapshot sources** → Finnhub profile market-cap, analyst price target, CME FedWatch remain excluded (not added). Tiingo/GDELT deferred for the historical-backfill reasons documented under "Resolved decisions"; the join is additive so they slot in later.
- **Placeholder scan:** no `TBD`/`TODO`. The one anchor stub in Task 3 Step 3 (`pull_insider` raising `NotImplementedError`) is explicitly called out to be removed in the same step.
- **Type consistency:** `ContextConfig`, `ContextBundle`, `build_context_features(bar_index, bundle, config)`, `context_feature_columns(config)`, `context_normalize_columns(config)`, `load_context_bundle(ticker, config, paths)`, `available_utc(day, lag_days)`, `build_ticker_dataset(ticker, bars, config, context=None)`, and `all_feature_columns(config)` are referenced identically across tasks. Canonical event-frame columns (`available_ts`/`published_ts`/`change`/`net_score`/`value`) match between the Task-2 producers, the Task-3 writers, and the Task-4 consumers.

---

## Memory note (after execution)

Update `~/.claude/projects/-Users-freddy-Documents-alphora/memory/alphora-5min-etl-ml-pipeline.md`: Plan B (context layer) complete on `conv/ghent`; record final test count and the two locked decisions (FRED lag-heuristic on daily series; Finnhub-only news, GDELT/Tiingo deferred).
