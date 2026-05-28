# Data Sources Ops Page — Design Spec

**Date:** 2026-05-27
**Status:** Approved (brainstorming complete)
**Scope:** Single feature slice. Frontend tab under `/data-health` + backend endpoints + new settings table.

## Problem

Operators cannot currently answer three questions on one screen:

1. Are our 17 external data providers actually connected and returning sane data right now?
2. What per-source switches and lookback windows are in effect?
3. For a given ticker, what does each source return _right now_, without waiting for the scheduled ingestion tick?

The existing `/data-health/providers` page renders only a static provider × tool matrix sourced from the periodic `data_health_pinger` writes. There is no manual trigger, no per-source configuration, and no place to inspect a payload.

## Goals

- One workspace where an operator types a ticker, hits "Pull All," and sees every ticker-scoped source resolve in parallel with status, count, latency, and a source-shaped preview.
- Per-source switches (enabled, lookback, notes) that persist server-side.
- Read-only visibility into whether each source's API key is configured (linking to the existing `/settings/api-keys` page for edits).
- Macro / event sources reachable from the same page, separately from the ticker workflow.

## Non-Goals

- Not rebuilding the existing provider × tool matrix. That stays at `/data-health/providers` (renamed to "Overview" tab).
- Not writing test-pull results to evidence tables. **Dry-run only.** Pulls hit the upstream API and return to the browser without touching `evidence_chunks`, `provider_checks`, or any other persistent table.
- Not wiring per-source `enabled` into scheduled ingestion in v1. It only filters the test-pull UI. Promoting it to a real kill switch is a follow-up.
- Not building per-user settings. Settings are global (one row per source).
- Not adding per-source params beyond lookback (form types, granularity, etc.). Per-source defaults remain hardcoded; we can layer specific knobs in later.

## User-Facing Surface

### Tab structure

`/data-health` becomes a tabbed page at the layout level:

- **Overview** (`/data-health/providers`) — existing provider × tool matrix, unchanged.
- **Sources** (`/data-health/sources`) — new workspace.

Tab navigation is a horizontal pill row under the page header. Tabs use existing `components/ui/tabs.tsx`. URLs do not change for the existing page; new page is added.

### `/data-health/sources` layout, top to bottom

1. **Header bar**
   - Left: ticker input (uppercased on blur, max 16 chars, accepts the same characters as `ProviderCheck.ticker`).
   - Center-right: "Pull All" primary button (disabled until ticker is non-empty), "Clear results" secondary button.
   - Right: count chips — `{n_enabled} enabled · {n_disabled} disabled`.

2. **Status strip** (sticky directly under the header)
   - One `StatusPill` per _enabled_ ticker-scoped source, in registry order.
   - States: `idle` (gray) · `loading` (animated) · `ok` (green, label: `12 · 412ms`) · `error` (red, label: `error`).
   - Hovering a pill shows the source label in a tooltip.

3. **Ticker-scoped sources** — provider-grouped accordion (using `components/ui/tabs.tsx`-style accordion or a new lightweight wrapper).
   - Each provider row collapses/expands; expanded by default.
   - Inside each provider, one row per feed (= ingestion handler). Each feed row contains:
     - Feed label + caption (one-line description).
     - Enable toggle.
     - Lookback select (`7d / 30d / 90d / 1y`, with sensible per-feed defaults).
     - API-key indicator: `✓ key configured` / `✗ key missing` / `n/a` (sources without a key requirement, e.g. SEC EDGAR), linking to `/settings/api-keys`.
     - Notes popover (freeform text, max 500 chars; saves on blur via `PATCH`).
     - "Pull" button (single source).
   - When a pull resolves, the row gets:
     - An inline `StatusPill` (success/error, count, latency).
     - An expandable result panel below the row.

4. **Result panel** (one per feed, expanded inline)
   - Source-shaped preview table (top 50 rows after server-side truncation). Per-feed column sets:
     - `finnhub_insider_transactions`: name · share · change · txn_date · txn_code · price.
     - `finnhub_news` / `tiingo_news_items`: headline · source · published_at.
     - `finnhub_peers`: peer ticker list (single column).
     - `finnhub_price_target`: target_low · target_mean · target_median · target_high · n_analysts · last_updated.
     - `finnhub_profile`: name · exchange · industry · market_cap · share_outstanding.
     - `finnhub_recommendation`: period · strong_buy · buy · hold · sell · strong_sell.
     - `polygon_aggregates`: t · o · h · l · c · v.
     - `sec_filings`: form · filed_at · accession · primary_doc.
     - Failed pulls render the error string instead of a table.
   - "View raw JSON" toggle reveals a `code-block` with the full (truncated) raw response.

5. **Macro / event sources** section at the bottom
   - Same accordion shape, no ticker input dependency. Ticker box value is ignored for these.
   - Includes: `fred_observations`, `fed_press`, `cme_fedwatch`, `kalshi_markets`, `polymarket_events`, `polymarket_price_history`, `congress_bills`.
   - Has its own "Pull All Macro" button.

### Behavior

- "Pull All" fans out N parallel browser fetches, one per enabled source. Each pill flips independently as it resolves.
- Within a provider, the browser serializes calls (Finnhub's six feeds run one after another) to be polite to the upstream rate limit; across providers, calls run in parallel.
- 30s timeout per source from the browser's perspective.
- Per-source button cooldown: 10s on the row's "Pull" button after click, to prevent accidental hammering.
- "Clear results" wipes the in-memory result state for the page but does not invalidate the server-side cache.

## Backend Surface

All endpoints live in a new route module `services/api/app/api/routes/data_sources.py`, registered with prefix `/data-sources` in `app/api/router.py`. Tag: `data-sources`.

### `GET /api/data-sources`

Returns the registry, joined with persisted settings.

Response shape (`DataSourceList`):

```jsonc
{
  "sources": [
    {
      "key": "finnhub_insider_transactions",
      "provider": "finnhub",
      "label": "Finnhub Insider Transactions",
      "caption": "Form 4 insider buys/sells for the symbol.",
      "scope": "ticker", // "ticker" | "macro"
      "default_lookback_days": 90,
      "api_key_env": "FINNHUB_API_KEY",
      "api_key_status": "configured", // "configured" | "missing" | "n/a"
      "preview_columns": [
        "name",
        "share",
        "change",
        "transaction_date",
        "transaction_code",
        "transaction_price",
      ],
      "settings": {
        "enabled": true,
        "lookback_days": 90,
        "notes": null,
        "updated_at": "2026-05-27T12:34:56Z",
      },
    },
  ],
}
```

The endpoint reads:

- Registry metadata from a new module `app/services/data_sources/registry.py` (see below).
- API key status from `app.config.get_settings()` (the same `*_api_key` fields the source clients already read).
- Persisted settings from `data_source_settings` table; sources without a row fall back to defaults.

### `PATCH /api/data-sources/{source_key}`

Updates persisted settings. Body (`DataSourceSettingsUpdate`):

```jsonc
{
  "enabled": true,
  "lookback_days": 30,
  "notes": "polygon throttling lately",
}
```

All fields optional. Validates `source_key` exists in registry; validates `lookback_days` in `{7, 30, 90, 365}`. Upserts the row in `data_source_settings`. Returns the same shape as a single entry from `GET /api/data-sources`.

### `POST /api/data-sources/{source_key}/test-pull`

Body (`DataSourceTestPullRequest`):

```jsonc
{
  "ticker": "AAPL", // required for "ticker"-scoped sources, ignored for "macro"
  "lookback_days": 30, // optional; falls back to per-source default
}
```

Response (`DataSourceTestPullResponse`):

```jsonc
{
  "source_key": "finnhub_insider_transactions",
  "status": "ok", // "ok" | "error"
  "latency_ms": 412,
  "count": 12,
  "as_of": "2026-05-27T12:34:56Z",
  "preview": [
    // rows shaped per `preview_columns`; truncated to top 50
    { "name": "TIM COOK", "share": 1000, "change": -200, "...": "..." },
  ],
  "raw": "...", // full raw JSON as string, truncated to 256 KB; null on error
  "error": null, // { "code": "...", "detail": "..." } when status="error"
}
```

Behavior:

- 422 if the source is `ticker`-scoped and `ticker` is missing or fails validation (`^[A-Z][A-Z0-9.\-]{0,15}$`).
- 404 if `source_key` is unknown.
- 409 if the source is currently disabled (`enabled = false` in settings). UI should not let this happen, but the server enforces.
- 503 if the source's API key is `missing`. Body uses the standard `{code, detail}` envelope.
- Otherwise, 200 with the response above.

Side effects:

- **Does not write to `evidence_chunks`, `provider_checks`, or any persistent table.** Dry-run only.
- Reads/writes the in-process or Redis-backed test-pull cache (see below).

## Data Model

### New table `data_source_settings`

Alembic migration: `020_data_source_settings.py`.

```python
op.create_table(
    "data_source_settings",
    sa.Column("source_key", sa.String(64), nullable=False),
    sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("lookback_days", sa.Integer(), nullable=True),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    ),
    sa.PrimaryKeyConstraint("source_key", name="pk_data_source_settings"),
)
```

`source_key` is the registry key (e.g., `finnhub_insider_transactions`). No FK — registry is in-code, not in DB.

### SQLAlchemy model

`app/db/models_data_sources.py` with a `DataSourceSettings` model. Follows the same shape as `models_settings.py`.

## Source Registry

New module `app/services/data_sources/registry.py`. Contains a single immutable list of entries:

```python
@dataclass(frozen=True)
class DataSourceEntry:
    key: str                                    # ingestion handler key, e.g. "finnhub_news"
    provider: str                               # e.g. "finnhub"
    label: str                                  # human label
    caption: str                                # one-line description
    scope: Literal["ticker", "macro"]
    default_lookback_days: int | None           # None for sources that don't accept a window
    api_key_env: str | None                     # the Settings field name, e.g. "finnhub_api_key"
    preview_columns: tuple[str, ...]
    fetcher: Callable[..., Awaitable[TestPullPayload]]  # the dry-run adapter
```

The registry is the single source of truth for both the `GET /api/data-sources` response and the dry-run orchestrator. Entries are listed in a fixed display order.

Initial entries (one per ingestion handler):

**Ticker-scoped:**

- `finnhub_insider_transactions`, `finnhub_news`, `finnhub_peers`, `finnhub_price_target`, `finnhub_profile`, `finnhub_recommendation`
- `polygon_aggregates`
- `sec_filings`
- `tiingo_news_items`

**Macro-scoped:**

- `fred_observations`, `fed_press`, `cme_fedwatch`, `kalshi_markets`, `polymarket_events`, `polymarket_price_history`, `congress_bills`

`gdelt` is included as ticker-scoped (uses the symbol as a query term).

## Dry-Run Orchestrator

New module `app/services/data_sources/test_pull.py`.

```python
@dataclass(frozen=True)
class TestPullPayload:
    rows: list[dict[str, object]]    # already shaped to preview_columns
    raw: str                          # full raw JSON, truncated client-side
    as_of: datetime | None

async def run_test_pull(
    *,
    source_key: str,
    ticker: str | None,
    lookback_days: int | None,
    http_client: httpx.AsyncClient,
) -> TestPullPayload
```

The orchestrator:

1. Looks up the registry entry.
2. Resolves effective lookback (`lookback_days` or `entry.default_lookback_days`).
3. Calls `entry.fetcher(...)` which wraps the existing source client function (`fetch_finnhub_company_news`, `fetch_polygon_aggregates`, etc.) and returns a `TestPullPayload`.
4. Each fetcher truncates `rows` to 200 entries and `raw` to 256 KB before returning. Cap is enforced inside the fetcher because the raw shape varies per source.

Crucially, fetchers call source clients directly and **never** invoke anything from `app/services/ingestion/` (the persistence path). This is what makes the path a dry run.

Fetchers are individually small wrappers because each source client function already returns parsed Pydantic models; the wrapper's job is to project to `preview_columns` and capture the raw bytes.

### Caching

Test-pull responses are cached server-side for 60s, keyed by `(source_key, ticker, lookback_days)`:

- If `redis_url` is reachable and a `Redis` client is available (the API process already has Redis via existing infra), cache in Redis under `data_sources:test_pull:{key}:{ticker}:{lookback}`.
- Otherwise, in-process LRU (max 256 entries).
- Cache hits skip the upstream API call entirely and return the stored response with the original `latency_ms` and `as_of` preserved.
- The cache exists to make refresh and back-button cheap, not to enforce rate limits.

## Frontend Implementation

### Tab routing

- `apps/web/app/(app)/data-health/layout.tsx` (new) — renders the page header + tab row + `{children}`.
- `apps/web/app/(app)/data-health/providers/page.tsx` — unchanged. (Becomes the "Overview" tab.)
- `apps/web/app/(app)/data-health/sources/page.tsx` (new) — server component, fetches `GET /api/data-sources` and passes to the client component below.
- `apps/web/app/(app)/data-health/page.tsx` — already redirects to `/data-health/providers`; keep as is.

### Client components

All under `apps/web/app/(app)/data-health/sources/`:

- `sources-workspace.tsx` — top-level client component. Owns ticker state, results map, "Pull All" handler. Renders header, status strip, accordion, macro section.
- `status-strip.tsx` — pills for enabled ticker-scoped sources. Pure, reads from props.
- `source-row.tsx` — one row in the accordion. Handles settings patch (debounced for notes, immediate for toggle/lookback), single pull, result panel toggle.
- `result-panel.tsx` — receives a test-pull response, renders the source-specific preview table and raw JSON toggle.
- `preview-tables.tsx` — exports a `Map<source_key, ColumnDef[]>` for the inline preview tables. Uses the existing `components/ui/data-table.tsx`.

### Pull orchestration

`lib/data-health/test-pull-client.ts` (new):

- `pullAll(ticker, sources)`: groups sources by provider, runs providers in parallel, feeds sequentially within a provider. Returns an `AsyncIterable` of `{source_key, result}` so the UI can flip pills as each one resolves.
- `pullOne(source_key, ticker, lookback)`: one call, 30s timeout (via `AbortController`), returns the typed response.
- Both wrap `getBrowserApi()` (the existing typed client).

### Schema regeneration

After backend lands, regenerate types per the existing flow:

1. `cd services/api && python -c "from app.main import app; import json; print(json.dumps(app.openapi()))" > openapi.json`
2. `npm run generate:api --workspace @alphora/web`

## Safety / Blast Radius

- Test-pulls are dry-run only; nothing persists to ingestion tables.
- Each source has its own existing rate limiter (via `_registry.get_rate_limiter`). The dry-run path goes through the same limiter, so a user spamming test pulls can only consume their share of the per-source budget.
- Per-source 10s button cooldown in the UI prevents finger-trigger spam.
- Server-side 60s cache makes refresh free.
- `enabled = false` is enforced on the server even though the UI also hides disabled sources.
- API responses are sanitized: rows truncated to 200, raw JSON truncated to 256 KB.

## Testing

### Backend

- Unit tests in `services/api/tests/test_data_sources_registry.py`: assert every ingestion handler has a registry entry; assert registry keys are unique; assert every entry's `api_key_env` is a real `Settings` field or `None`.
- Unit tests in `services/api/tests/test_data_sources_routes.py`:
  - `GET /api/data-sources` shape, settings fallback, api-key status reflection.
  - `PATCH /api/data-sources/{key}` validates `lookback_days`, rejects unknown source, persists and returns row.
  - `POST .../test-pull` covers: success, missing-api-key 503, unknown-source 404, missing-ticker 422, disabled 409, cache hit.
- Unit tests in `services/api/tests/test_data_sources_test_pull.py`: each fetcher's projection to `preview_columns`, truncation behavior, raw size cap.
- Mocked source clients via existing patterns in `services/api/tests/` (the repo already mocks `httpx` heavily for source-client tests).

### Frontend

- `apps/web/test/data-health/sources-workspace.test.tsx`: rendering of status strip, accordion, "Pull All" fan-out (mock `pullOne`).
- `apps/web/test/data-health/preview-tables.test.tsx`: column definitions match `preview_columns` from a fixture registry response.
- `apps/web/e2e/data-health-sources.spec.ts` (Playwright): set ticker `AAPL`, click "Pull All", assert at least three pills resolve to `ok` (with mocked API), assert one panel expands and shows rows.

## Out of Scope (Explicit)

- Per-user settings.
- Per-source params beyond lookback.
- Rate-limit overrides.
- Wiring `enabled` into the scheduled ingestion path.
- Persisting test-pull results across reloads beyond the 60s cache.
- Adding the Overview tab a settings filter (matrix stays as-is).
- New source clients. Only existing source clients are exposed.

## Open Follow-ups (Not in v1)

- Promote `enabled` to a hard kill switch consumed by `data_health_pinger` and the ingestion workers.
- Add a "Re-pull stale only" button that ignores cache.
- Add per-source params (SEC form types, Polygon timeframe) once we know which ones operators actually want to tweak.
- Surface the last 5 test-pull results per source in a small history strip (currently we only keep the latest in cache).
