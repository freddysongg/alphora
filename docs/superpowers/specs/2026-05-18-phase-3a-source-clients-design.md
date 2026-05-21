# Phase 3a — Source-Client Foundation + FRED + SEC EDGAR

**Date:** 2026-05-18
**Branch:** `freddysongg/trading-llm-signals`
**Parent plan:** `.context/attachments/plan.md` Phase 3 — Ingestion, Extraction, And Entity Resolution
**Spec:** `.context/attachments/research-funnel-spec.md` Sections 7, 9, 10
**Predecessor:** Phase 2 handoff `.context/attachments/phase-2-handoff.md`

Phase 3 is decomposed into 3a–3f (see Phase 2 handoff "Next Up"). This document specifies **3a only**.

## Goal

Land a reusable foundation for outbound source-client HTTP, then prove it with two anchor providers: **FRED** (macro time series) and **SEC EDGAR** (filings + CIK registry).

3b will wire these clients into `evidence` / `evidence_chunks` ingestion. 3c will reuse SEC EDGAR's CIK lookup for entity bootstrap. 3f will fill in the remaining seven providers on the same foundation.

## Non-Goals

- No persistence into `evidence` / `evidence_chunks` (that is 3b).
- No entity bootstrap (that is 3c).
- No LLM calls (that is 3d).
- No new API routes, no SSE wiring, no UI changes.
- No worker dispatch wiring; clients are libraries, not background jobs yet.
- No additional clients beyond FRED and SEC EDGAR. The rest land in 3f.
- No retries on 4xx (other than 429); only 5xx and connect/read timeouts.
- No circuit-breaker, no metrics export, no caching layer. Plain idempotent retries.

## Module Layout

```
services/api/app/services/source_clients/
├── __init__.py              # re-exports public fetch_* functions and public types
├── _http.py                 # request helpers, retry loop, content_hash, errors
├── _rate_limit.py           # asyncio token-bucket limiter
├── fred.py                  # FRED client: fetch_series_observations, FredSeriesObservations
└── sec_edgar.py             # SEC EDGAR client: fetch_company_tickers, fetch_submissions, etc.

services/api/tests/
├── test_source_clients_http.py        # retry, timeout, status-code handling
├── test_source_clients_rate_limit.py  # token-bucket behavior, deterministic clock
├── test_source_clients_fred.py        # FRED happy path + errors (respx)
└── test_source_clients_sec_edgar.py   # SEC EDGAR happy path + UA + errors (respx)
```

Why a sub-package: 3f will add eight more provider modules. Flat `app/services/` already has 9 files; another 10 here makes it noisy. Sub-package mirrors stdlib (`urllib`, `http`).

Why leading underscores on `_http.py` / `_rate_limit.py`: signals internal. Only `fetch_*` functions and their response models are public API. `__init__.py` decides what `from app.services.source_clients import …` exposes.

Why free functions (no classes): matches existing `app/services/*` style (`budget.py`, `market_clock.py`, `model_pricing.py` — no class hierarchies). A `BaseSourceClient` ABC would silently introduce a new convention.

## Public API Shape

```python
# app/services/source_clients/__init__.py
from app.services.source_clients.fred import (
    FredObservation,
    FredSeriesObservations,
    fetch_series_observations,
)
from app.services.source_clients.sec_edgar import (
    SecCompanyTicker,
    SecCompanyTickersResponse,
    SecSubmissionsResponse,
    fetch_company_tickers,
    fetch_submissions,
)

from app.services.source_clients._http import (
    SourceClientConfigError,
    SourceClientError,
    SourceClientHTTPError,
    SourceClientRateLimitError,
    SourceClientTimeoutError,
)

__all__ = [
    "FredObservation",
    "FredSeriesObservations",
    "SecCompanyTicker",
    "SecCompanyTickersResponse",
    "SecSubmissionsResponse",
    "SourceClientConfigError",
    "SourceClientError",
    "SourceClientHTTPError",
    "SourceClientRateLimitError",
    "SourceClientTimeoutError",
    "fetch_company_tickers",
    "fetch_series_observations",
    "fetch_submissions",
]
```

Errors are re-exported from the package root so callers can `from app.services.source_clients import SourceClientError` without importing the leading-underscore internal module.

Callers (Phase 3b ingestion, Phase 3c bootstrap, Phase 4 macro brief) import only from `app.services.source_clients`.

## Shared Utilities — `_http.py`

### Errors

A small typed error hierarchy. No exceptions leak from `httpx` to callers.

```python
class SourceClientError(Exception):
    """Base for all source-client errors."""

class SourceClientHTTPError(SourceClientError):
    """Non-retryable HTTP failure (4xx other than 429, or 5xx after retries)."""
    status_code: int
    url: str
    body_excerpt: str  # first 512 chars, for logs

class SourceClientTimeoutError(SourceClientError):
    """Connect or read timeout after retries."""
    url: str

class SourceClientRateLimitError(SourceClientError):
    """429 after retries exhausted."""
    url: str
    retry_after_seconds: float | None

class SourceClientConfigError(SourceClientError):
    """Raised when a required key/setting is missing at call time."""
    setting_name: str
```

Callers catch `SourceClientError` for "anything broke", or the specific subclass when behavior differs (e.g. 3b may treat timeout differently from 4xx).

### Request helper

```python
@dataclass(frozen=True)
class HttpRequestConfig:
    method: Literal["GET", "POST"]
    url: str
    params: Mapping[str, str | int | float] | None = None
    headers: Mapping[str, str] | None = None
    json_body: Mapping[str, object] | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3            # for 5xx, 429, connect/read timeouts
    backoff_base_seconds: float = 0.5  # exponential: 0.5, 1.0, 2.0, ...
    backoff_max_seconds: float = 8.0

@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body_bytes: bytes
    headers: Mapping[str, str]
    content_hash: str               # sha256 hex of body_bytes
    url: str                        # final URL after any redirects

async def request(
    client: httpx.AsyncClient,
    config: HttpRequestConfig,
    *,
    rate_limiter: RateLimiter | None = None,
) -> HttpResponse: ...
```

Retry policy:
- Retry on `httpx.ConnectError`, `httpx.ReadTimeout`, `httpx.RemoteProtocolError`, `httpx.HTTPStatusError` where status ∈ {429, 500, 502, 503, 504}.
- Exponential backoff with full jitter: `sleep = random.uniform(0, min(backoff_max, base * 2**attempt))`.
- For 429 specifically, honor `Retry-After` header if present (seconds form only — HTTP-date form is in scope to *parse* but we expect FRED/EDGAR to use seconds).
- Raise typed error after `max_retries` exhausted.

Why `frozen=True` dataclasses: matches Phase 1 / Phase 2 schema/value-object style.
Why `httpx.AsyncClient` is caller-injected: Phase 3b will want to share a client across many requests in one run; this keeps connection pooling under the caller's control.

### Content hash

`content_hash` is computed inside `request()` once, on the raw response bytes. Sha-256, lowercase hex, no length prefix. Matches the `evidence.content_hash` column shape from Phase 2.

Reason for hashing here: every caller in Phase 3b will need this same hash to do idempotency checks against `evidence.content_hash`. Centralizing it removes a footgun (one caller hashing post-decode while another hashes pre-decode → different hashes for the same body).

## Shared Utilities — `_rate_limit.py`

Asyncio token-bucket. Simple, well-understood, deterministic in tests with an injected clock.

```python
class RateLimiter:
    def __init__(
        self,
        *,
        rate_per_second: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None: ...

    async def acquire(self) -> None:
        """Block until a token is available, then consume one."""
```

Behavior:
- Bucket starts full (`burst` tokens).
- Tokens refill at `rate_per_second` continuously.
- `acquire()` deducts one token; if none available, sleeps the minimum time required for one to arrive.
- Concurrency-safe via an internal `asyncio.Lock` around the token math.

`clock` and `sleep` injected for tests — pass a fake monotonic clock and a no-op sleep that captures the requested duration.

Each provider module owns its own `RateLimiter` instance (module-level singleton), sized per the provider's documented limit minus a safety margin.

- **FRED**: 120 req/min → `rate_per_second=2.0`, `burst=10`.
- **SEC EDGAR**: 10 req/sec → `rate_per_second=8.0`, `burst=5`. (Slight safety margin under the 10-req/sec docs limit.)

Module-level singletons (vs caller-supplied) because the limit is a *provider-wide* concern, not a per-request one. A second concurrent caller in the same process must share the bucket.

## FRED Client — `fred.py`

**API base:** `https://api.stlouisfed.org/fred/`
**Auth:** `api_key=<key>` query parameter. Key read from `settings.fred_api_key` (added to `app/config.py`).
**Docs:** https://fred.stlouisfed.org/docs/api/fred/

Public function:

```python
async def fetch_series_observations(
    *,
    client: httpx.AsyncClient,
    series_id: str,
    observation_start: date | None = None,
    observation_end: date | None = None,
) -> tuple[FredSeriesObservations, str]:
    """Returns parsed payload and content_hash for idempotency."""
```

Returns a 2-tuple of `(parsed_model, content_hash)` because callers in 3b will need *both* the parsed shape (to write structured columns) and the raw-body hash (to idempotency-check against `evidence.content_hash`).

Response models (Pydantic v2, `model_config = ConfigDict(frozen=True, extra="ignore")`):

```python
class FredObservation(BaseModel):
    date: date
    value: Decimal | None  # FRED returns "." for missing; we map to None
    realtime_start: date
    realtime_end: date

class FredSeriesObservations(BaseModel):
    series_id: str
    observation_start: date
    observation_end: date
    count: int
    observations: list[FredObservation]
```

Pydantic `extra="ignore"` because FRED adds fields over time (e.g. `units`, `frequency`) — we don't want a third-party response evolution to break extraction.

`Decimal | None` for `value` because financial data deserves Decimal; FRED returns `"."` for missing observations (mapped to `None` via a validator).

Error mapping:
- 400 `Bad Request` (invalid `series_id`) → `SourceClientHTTPError` (no retry).
- 404 → `SourceClientHTTPError`.
- 429 / 5xx → retried by `_http.request`; final raise is `SourceClientRateLimitError` / `SourceClientHTTPError`.

## SEC EDGAR Client — `sec_edgar.py`

**API base:** `https://data.sec.gov/` and `https://www.sec.gov/`
**Auth:** none — but **must** send a `User-Agent: Alphora Research Desk admin@alphora.local` header or SEC returns 403. UA string read from `settings.sec_edgar_user_agent` (added to `app/config.py`, with a sensible default for dev).
**Docs:** https://www.sec.gov/os/accessing-edgar-data

Two public functions for 3a — pick the smallest pair that exercises both the JSON-listing path (needed for 3c CIK bootstrap) and the per-filer submissions path (needed for 3b ingestion of 10-Ks).

```python
async def fetch_company_tickers(
    *, client: httpx.AsyncClient,
) -> tuple[SecCompanyTickersResponse, str]:
    """GET https://www.sec.gov/files/company_tickers.json
       Returns the registry of ~10k US-listed companies with CIK + ticker.
       Used by 3c entity bootstrap."""

async def fetch_submissions(
    *, client: httpx.AsyncClient, cik: str,
) -> tuple[SecSubmissionsResponse, str]:
    """GET https://data.sec.gov/submissions/CIK{padded_cik}.json
       Returns the recent filings list for one company.
       Used by 3b ingestion."""
```

`cik` is the unpadded CIK (e.g. `"320193"` for Apple); we zero-pad to 10 digits internally — that's the URL convention SEC mandates.

Response models:

```python
class SecCompanyTicker(BaseModel):
    cik_str: int        # SEC returns int; we keep it as int
    ticker: str
    title: str          # company legal name

class SecCompanyTickersResponse(BaseModel):
    """The JSON shape is {{"0": {{...}}, "1": {{...}}}}.
    We flatten to a list[SecCompanyTicker] in a model_validator."""
    companies: list[SecCompanyTicker]

class SecRecentSubmission(BaseModel):
    accession_number: str   # JSON field: "accessionNumber"
    filing_date: date
    report_date: date | None
    form: str               # "10-K", "10-Q", "8-K", ...
    primary_document: str
    primary_doc_description: str | None

class SecSubmissionsResponse(BaseModel):
    cik: str
    name: str
    sic: str | None
    tickers: list[str]
    recent: list[SecRecentSubmission]
```

The SEC `company_tickers.json` is a dict-of-dicts keyed by string indices. We flatten it via a Pydantic `model_validator(mode="before")` so callers see a clean `list[SecCompanyTicker]`.

`SecSubmissionsResponse.recent` is flattened from the wire format which uses parallel arrays (`recent.accessionNumber: list[str]`, `recent.filingDate: list[str]`, …). Validator transposes these arrays into row-oriented records. This is a known SEC quirk; the flattening lives in the client (not the caller) so 3b never sees the column-oriented shape.

## Configuration — `app/config.py` additions

```python
class Settings(BaseSettings):
    # … existing fields …
    fred_api_key: SecretStr | None = None
    sec_edgar_user_agent: str = "Alphora Research Desk admin@alphora.local"
```

`fred_api_key` is `SecretStr` because it's an actual credential. `None` is allowed because dev environments may not have one set; callers that need it raise a typed error (see "Missing-key behavior" below).

`sec_edgar_user_agent` is plain `str` because it's not a secret — it's a courtesy identifier. Default value works fine for dev; production overrides via env.

### Missing-key behavior

When `fetch_series_observations` is called and `settings.fred_api_key` is `None`, `SourceClientConfigError(setting_name="fred_api_key")` is raised immediately, before any HTTP attempt. Caller (3b / 3c / 3d) decides whether to log+skip or fail the run.

SEC EDGAR has no required key (only `sec_edgar_user_agent`, which has a default), so it never raises `SourceClientConfigError`.

## Testing Strategy

Per-file targets:

### `test_source_clients_http.py`
- `request()` returns `HttpResponse` with correct status / body / hash on 200.
- Retries 5xx → eventual 200.
- Retries connect timeout → eventual 200.
- Retries exhausted on persistent 503 → `SourceClientHTTPError(status_code=503)`.
- 429 with `Retry-After: 2` → respects header, sleeps ≥ 2s on first retry (deterministic via fake clock).
- 404 does **not** retry → immediate `SourceClientHTTPError(status_code=404)`.
- `content_hash` is sha-256 hex of raw body bytes.
- Backoff bounded by `backoff_max_seconds`.

### `test_source_clients_rate_limit.py`
- Initial burst of `burst` requests proceeds without sleeping.
- The `burst+1`-th request sleeps `1 / rate_per_second` seconds.
- Concurrent `acquire()` calls serialize correctly (no token underflow).
- Sleeps are deterministic via injected clock + capturing sleep fake.

### `test_source_clients_fred.py` (using `respx`)
- Happy path: `fetch_series_observations(series_id="GDP")` parses observations, missing `"."` → `None`.
- Date filtering passes through `observation_start` / `observation_end` query params.
- Missing `FRED_API_KEY` → `SourceClientConfigError` before HTTP attempt.
- 400 invalid series → `SourceClientHTTPError(status_code=400)` (no retry).
- Content hash returned matches sha-256 of mocked body.

### `test_source_clients_sec_edgar.py` (using `respx`)
- `fetch_company_tickers` flattens dict-of-dicts → `list[SecCompanyTicker]`.
- `fetch_submissions(cik="320193")` zero-pads to `"CIK0000320193"` in URL.
- Column-oriented `recent` arrays → row-oriented `list[SecRecentSubmission]`.
- Request includes the configured `User-Agent` header.
- 403 (UA missing or bad) → `SourceClientHTTPError(status_code=403)` (no retry, no key error — UA is configured).

Hashing-related expectation in both client tests: every public `fetch_*` returns `(model, content_hash)` and the hash matches `hashlib.sha256(body_bytes).hexdigest()`.

Target test count: roughly **18–22 new tests**, bringing total from 219 → ~237–241.

## Verification Gates

From `services/api`:
- `pytest`: all existing 219 + new 3a tests pass.
- `ruff check`: clean.
- `mypy app`: strict clean (will include the new sub-package's 4 modules).
- Alembic: unchanged (no migration in 3a — no schema changes).

## Known Cross-Cuts With Phase 2 Substrate

3a writes nothing to the DB. But its output is shaped to land cleanly in Phase 2's `evidence` table when 3b arrives:

- `content_hash` (sha-256 hex) matches `evidence.content_hash` column.
- Callers in 3b will set `evidence.source = "fred"` / `"sec_edgar"` and `evidence.document_id` = the source-native ID (FRED series_id + start/end window, SEC accession_number).
- `raw_blob_ref` (object store key) is out of scope here; 3b decides whether to persist body bytes inline or to blob storage.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| `respx` mock drift from real provider response shape | Capture one real response per endpoint as a fixture (committed); load it in tests. Re-capture only when SEC/FRED documents a change. |
| Rate-limit math drift between provider-doc and actual enforcement | Conservative defaults below documented limits (FRED 2 rps vs documented ~2 rps; SEC 8 rps vs documented 10 rps). |
| `httpx.AsyncClient` lifecycle bugs when callers forget `aclose()` | Callers in 3b use `async with httpx.AsyncClient() as client:` — documented in 3a's `__init__.py` docstring; tests use the same pattern. |
| Pydantic `extra="ignore"` hides genuinely broken responses | Trade-off accepted: prefer "ignore unexpected fields" over "blow up on a new field". Logged via structlog at debug level (does not require config change in 3a). |

## Out-Of-Scope Items Carried Forward To 3b–3f

- Evidence persistence + chunking — **3b**.
- Structural chunking strategy per source type (10-K by Item, news by paragraph, Congress filing by transaction line, FOMC by section) — **3b** per Section 9 step [2].
- Entity bootstrap from SEC + GLEIF + ticker registries — **3c**.
- LlmClient integration + cited extraction + deterministic verifier — **3d**.
- Entity resolution pipeline (5 steps) — **3e**.
- Entity merge mechanism + remaining 7 source clients (Polygon, Tiingo, Ainvest, Kalshi, Congress.gov, Polymarket, OpenFIGI, GLEIF) — **3f**.

## File Map

```
services/api/
├── app/
│   ├── config.py                                          # MODIFIED: add fred_api_key, sec_edgar_user_agent
│   └── services/source_clients/                           # NEW package
│       ├── __init__.py                                    # NEW
│       ├── _http.py                                       # NEW
│       ├── _rate_limit.py                                 # NEW
│       ├── fred.py                                        # NEW
│       └── sec_edgar.py                                   # NEW
└── tests/
    ├── test_source_clients_http.py                        # NEW
    ├── test_source_clients_rate_limit.py                  # NEW
    ├── test_source_clients_fred.py                        # NEW
    └── test_source_clients_sec_edgar.py                   # NEW
```

Estimated diff size: ~700–900 insertions, 0 deletions, no existing-file rewrites beyond `app/config.py` (one settings group added).
