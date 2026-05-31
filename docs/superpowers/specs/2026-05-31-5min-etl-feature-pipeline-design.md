# 5-min ETL & Feature Pipeline — Design

**Date:** 2026-05-31
**Status:** Approved (brainstorming → spec)
**Scope:** ETL / feature-engineering / labeling pipeline only. This is phase 1 of a
larger effort to train an XGBoost model on 5-minute bars and run live inference for
P&L decisions. Model training, evaluation, and live inference are **separate, later
specs**.

---

## 1. Goal

Produce a reproducible, leakage-free **labeled feature dataset** from the project's
existing data providers, at **5-minute** granularity, across a curated universe of
liquid tickers. The dataset is the input to a later XGBoost training phase.

The single design driver is correctness: a 5-min trading dataset that looks great in
backtest but leaks future information will lose money live. Every decision below is
made to prevent look-ahead bias.

---

## 2. Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Sequencing | ETL/feature pipeline first; training + live inference are later cycles |
| Prediction target | Triple-barrier (did price hit profit target before stop within a horizon) |
| Barrier sizing | ATR / volatility-scaled (generalizes across tickers) |
| Universe | Liquid large-caps + major ETFs (~100–300 names) |
| Model structure | Single pooled model, per-ticker normalized features |
| History depth | 6–12 months of 5-min bars (fast first cut) |
| Feature scope | Price spine + curated, strictly point-in-time context layer |
| ETL backbone | Offline parquet feature store (no Postgres writes) |
| Label form | Binary `barrier_label ∈ {1 = upper first, 0 = lower first or timeout}` |
| Barrier defaults | `pt_mult=2.0`, `sl_mult=1.0`, `H=12` bars (1 hour), all config-driven |

---

## 3. What we reuse (do not rebuild)

- `app.services.source_clients.polygon.fetch_polygon_aggregates(... multiplier, timespan, from_date, to_date, adjusted)`
  — the 5-min bar fetcher, with a built-in rate limiter (4 req/s, burst 5).
- `app.services.source_clients.polygon.fetch_polygon_tickers` — universe validation (`active=true`).
- `app.indicators` — `adx, atr, bollinger, ema, macd, rsi, vwap` (warmup-masked, parity-tested).
- `app.services.market_clock` — `to_et`, `RTH_OPEN_ET_MIN`, `RTH_CLOSE_ET_MIN` (session-aware logic).
- Source clients for Finnhub, Tiingo, GDELT, FRED (already implemented).
- `app.config.get_settings()` for API keys; `typer` CLI pattern (`app.cli.main`); `uv`; Python 3.12; mypy `strict`.

---

## 4. Module layout

New subpackage `services/api/app/ml/` inside the API service. Reuses `app.*` directly;
no cross-service imports; no Postgres writes.

```
services/api/app/ml/
  __init__.py
  config.py            # frozen dataclasses: universe, date range, barrier params, feature params, paths
  universe.py          # resolve curated liquid universe (+ optional Polygon active-ticker filter)
  extract/
    __init__.py
    bars.py            # Polygon 5-min bulk loader (date-windowed pagination) -> raw parquet
    context.py         # point-in-time-safe context extractor -> per-source parquet
  features/
    __init__.py
    price.py           # returns, ranges, gaps, volume, realized vol
    technical.py       # wraps app.indicators -> rsi/macd/adx/atr/%B/ema-ratios
    context_join.py    # merge_asof (backward) of context onto bar grid
    normalize.py       # CAUSAL per-ticker normalization (rolling stats, never global)
  labels/
    __init__.py
    triple_barrier.py  # ATR-scaled, session-aware triple-barrier labeler
  assemble.py          # orchestrate stages -> labeled dataset + manifest + feature_spec
  storage.py           # parquet IO + path conventions
  cli.py               # typer app -> registered in pyproject as `alphora-etl`
```

Output (git-ignored) under the existing `services/api/data/`:

```
data/ml/raw_bars/5min/<ticker>.parquet
data/ml/context/<source>/<ticker>.parquet        # ticker-scoped sources
data/ml/context/<source>.parquet                  # macro sources (FRED)
data/ml/datasets/<run_id>/dataset.parquet
data/ml/datasets/<run_id>/manifest.json
data/ml/datasets/<run_id>/feature_spec.json
```

`services/api/.gitignore` gains `data/ml/` so generated parquet is never committed.

---

## 5. Pipeline stages (data flow)

### 5.1 Universe resolution (`universe.py`)
- Start from a curated static list of liquid large-caps + major ETFs (SPY/QQQ/sector
  ETFs), defined as a constant in `universe.py` (or a small committed CSV under
  `app/ml/`).
- Optionally validate/filter each ticker via `fetch_polygon_tickers` (`active=true`).
- Output: a deterministic, ordered `tuple[str, ...]` of tickers.

### 5.2 Raw bar extraction (`extract/bars.py`)
- For each ticker, call `fetch_polygon_aggregates(multiplier=5, timespan="minute",
  from_date, to_date, adjusted=True)`.
- **Pagination by date windows:** Polygon caps roughly 50k rows/request; chunk the
  requested date range (e.g. monthly windows) so each request stays under the cap, then
  concatenate. Respect the existing rate limiter.
- **Idempotent:** write per-ticker parquet; skip or refresh based on the existing file
  and the requested range.
- **RTH-only by default:** tag each bar with `is_rth` via `market_clock`; the feature
  and label stages operate on RTH bars only for the first cut (overnight 5-min bars are
  gappy/illiquid). A flag can disable RTH filtering later.
- Columns: `timestamp` (UTC `DatetimeIndex`), `open, high, low, close, volume`.
- Empty responses / missing tickers are logged and skipped, never fatal.

### 5.3 Context extraction (`extract/context.py`)
Only **point-in-time-safe** sources are included in the training feature set — sources
that carry a real event timestamp, so a value can be attributed to the moment it
actually became known:

- **Insider transactions** (Finnhub) — keyed by `transaction_date` / filing date →
  recency + net buy/sell intensity, forward-filled from filing date.
- **News / article volume** — Finnhub `published_at`, Tiingo `publishedDate`, GDELT
  `seendate` → rolling counts in trailing windows ending at bar *t*.
- **Finnhub recommendation trend** — monthly `period` → forward-fill the latest period
  whose date ≤ bar date.
- **FRED macro** — dated observations + realtime vintages → forward-fill the latest
  observation with `realtime_start ≤ bar date`.

Each source is stored as parquet with its real event timestamp so the join stage can do
a strictly-backward as-of merge.

### 5.4 Feature engineering (`features/`)
See section 6.

### 5.5 Labeling (`labels/triple_barrier.py`)
See section 7.

### 5.6 Assembly (`assemble.py`)
- Drop warmup rows (indicator NaNs) and the unlabeled session tail.
- Concatenate per-ticker labeled frames into one dataset (single parquet for the first
  cut; partition by ticker/month only if memory pressure demands it).
- Deterministic row ordering (`ticker`, `entry_ts`) for reproducibility.
- Write `dataset.parquet`, `manifest.json`, `feature_spec.json`.

---

## 6. Feature families

All features are **causal** — computed only from data at or before bar *t*'s close.

**Price / volume** (`features/price.py`): log-returns over {1, 3, 6, 12} bars; high-low
range / close; close vs session VWAP; gap from prior close; volume; relative volume (vs
rolling 20-bar mean); rolling realized volatility.

**Technical** (`features/technical.py`, wrapping `app.indicators`): `rsi(14)`;
`macd(12,26,9)` line / signal / histogram; `adx(14)`; `atr(14)` (also feeds the
labeler); Bollinger %B (from `bollinger`); EMA ratios (`close/ema20`, `ema9/ema20`).

**Session / time**: minutes since RTH open; time-of-day bucket; day-of-week;
`is_first_30min` / `is_last_30min` flags.

**Context** (`features/context_join.py`, joined via backward `merge_asof`): insider
buy/sell recency + net intensity; trailing news/article counts (multiple windows);
Finnhub recommendation trend; FRED macro levels and changes.

**Normalization** (`features/normalize.py`): per-ticker z-scoring using **rolling /
expanding statistics over past bars only** — never full-sample statistics (the most
common silent leak). Scale-free features (returns, RSI, %B) skip normalization.

---

## 7. Triple-barrier labeling

For each entry bar *t*:

- `ATR_t = atr(14)` evaluated at *t*.
- Upper barrier = `close_t + pt_mult · ATR_t`; lower barrier = `close_t − sl_mult · ATR_t`;
  vertical barrier = *t + H* bars.
- **Defaults:** `pt_mult = 2.0`, `sl_mult = 1.0`, `H = 12` bars (1 hour at 5-min) — all
  config-driven.
- Walk bars **strictly after** *t*, **capped at the RTH session close** (the vertical
  barrier never spans overnight). First barrier touched wins.
- **Primary label:** `barrier_label ∈ {1 = upper hit first, 0 = lower hit first or
  timeout}` (binary, decision-aligned: "does a long entry hit its target before its
  stop?").
- Also stored per row: `touch_type ∈ {upper, lower, vertical}`; `label_return` (realized
  return at touch); `label_end_ts` (touch time — lets the training phase compute
  sample-uniqueness weights for overlapping labels); `atr_at_entry`.
- The last *H* bars of each session cannot be labeled → dropped.

---

## 8. Output schema

One row per labeled entry bar:

```
ticker, entry_ts (UTC), session_date,
<feature columns…>,
barrier_label, touch_type, label_return, label_end_ts, atr_at_entry
```

- `manifest.json`: `run_id`, git sha, all params, date range, universe, per-ticker row
  counts, overall label balance.
- `feature_spec.json`: ordered feature list, dtypes, and a normalized flag per feature.

---

## 9. Leakage invariants (enforced and tested)

1. Every feature input timestamp ≤ `entry_ts`; every label input timestamp > `entry_ts`.
2. `merge_asof` direction = backward; context forward-filled only from its real event time.
3. Normalization statistics are causal (rolling), never global.
4. No imputation using future rows.
5. Forward returns start at *t + 1*; entry is priced at *t*'s close.

---

## 10. Tests (pytest, matching repo conventions)

- Synthetic price series with hand-computed barrier outcomes → assert `barrier_label`
  and `touch_type` correct.
- Assert no labeled row carries feature data dated after `entry_ts`.
- Assert session-tail rows are unlabeled and dropped.
- Assert the vertical barrier never spans a session boundary.
- Golden-fixture test on a tiny multi-ticker sample for full-pipeline determinism.
- Context join: assert an event dated after a bar never appears in that bar's features.

---

## 11. Dependencies, CLI, config

- **Deps:** add `pyarrow` to a new `[project.optional-dependencies] ml` extra.
  `xgboost` / `scikit-learn` are deferred to the training-phase spec. pandas / numpy are
  already present transitively via `pandas-ta`.
- **CLI** (`alphora-etl`, typer, registered in `pyproject [project.scripts]`):
  - `pull-bars` — fetch + cache raw 5-min bars for the universe.
  - `pull-context` — fetch + cache point-in-time context sources.
  - `build-dataset` — feature + label + assemble into a labeled dataset run.
  - `run` — chain all stages from a config file.
- **Config:** frozen dataclasses in `app/ml/config.py`; defaults overridable via CLI
  flags / a config file.

---

## 12. Risks & honest caveats

- **Single regime.** 6–12 months covers only one market regime. Generalization should
  not be trusted until history is extended; the architecture supports deeper pulls.
- **Snapshot-only sources excluded.** Finnhub profile market-cap, analyst price target,
  and CME FedWatch current probabilities expose only "current" snapshots and cannot be
  safely backfilled into a historical training set (look-ahead). They are deferred to
  the live-inference phase, where "current" is correct.
- **Context signal at 5-min is weak.** Daily/event-level context is slow-moving relative
  to 5-min bars; it is included as carefully-lagged context, not as a primary driver.
  The price/volume + technical spine is the workhorse.
- **Costs.** ATR-scaled targets for liquid names typically clear spread + commission,
  but transaction costs are handled at the later decision/backtest layer, not in
  labeling.

---

## 13. Out of scope (later specs)

XGBoost training, hyperparameter tuning, model evaluation / backtest, live inference,
and execution.
