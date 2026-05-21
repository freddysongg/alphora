# Phase 3c — Entity Bootstrap from Authoritative Registries

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-3c-entity-bootstrap` (off `origin/freddysongg/trading-llm-signals` @ `cbf3982`)
**Parallel coordination:** `docs/superpowers/phase-3-parallel-coordination.md`
**Spec section:** `.context/attachments/research-funnel-spec.md` §10 ("Bootstrap from authoritative registries")
**Plan reference:** `.context/attachments/plan.md` Phase 3 item 4

## Goal

Seed the `entities` table with canonical entities from authoritative registries BEFORE any LLM extraction runs. Each bootstrapped entity gets:

- A stable `external_ids` dict (e.g. `{"cik": "0000320193", "ticker": "AAPL"}`).
- A rich `aliases` list (legal name + common variants).
- `confidence = 1.0` and `needs_review = false` — these are authoritative.

Bootstrap is what enables Step 1 (alias match) and Step 2 (external-ID match) of Phase 3e's resolution pipeline to hit ~80% of candidates.

## Non-Goals

- No LLM calls.
- No new HTTP clients (3a + 3f own those).
- No new tables, no migrations.
- No fuzzy matching (3e).
- No relation creation. This phase only creates entities, not relations between them. `belongs_to_sector` edges and similar are out of scope.
- No data refresh / scheduler. Bootstrap is invoked once per registry as a setup step.
- No country/regulator entities for v0 (those are static seed data — handled as a thin Python-bundled list, not a registry fetch).

## Sources of canonical entities

| Registry | Source | Entity type | external_ids keys | Phase 3a or 3f client |
|---|---|---|---|---|
| SEC CIK list | `fetch_company_tickers` | `company` | `cik`, `ticker` | **3a (available now)** |
| GICS sectors/industries | static file bundle | `sector` | `gics_code` | none — bundled |
| ISO country codes | static file bundle | `country` | `iso_alpha2` | none — bundled |
| GLEIF LEI registry | `fetch_gleif_lei` | `company` | `lei` | **3f (mock until merge)** |
| Polygon tickers | `fetch_polygon_tickers` | `company` (with ticker) | `polygon_id`, `ticker` | **3f (mock until merge)** |
| Tiingo tickers | `fetch_tiingo_tickers` | `company` | `tiingo_id`, `ticker` | **3f (mock until merge)** |
| Congress bioguide | `fetch_congress_members` | `person` | `bioguide_id` | **3f (mock until merge)** |

3c implements all 7 bootstrap functions. The 4 that depend on 3f clients call those clients **through an injected callable** so 3c's tests can mock them with `respx` against the documented endpoint shapes. When 3f integrates, the injected callables become the real `fetch_*` from 3f.

## Module Layout

```
services/api/app/services/entity_bootstrap/
├── __init__.py              # public bootstrap_* functions + BootstrapError
├── _persist.py              # insert_or_get_entity (idempotent on external_id)
├── _normalize.py            # normalize_company_name(), normalize_alias_set()
├── sec_cik.py               # bootstrap_from_sec_cik (uses Phase 3a fetch_company_tickers)
├── gleif.py                 # bootstrap_from_gleif (injects fetcher)
├── polygon_tickers.py       # bootstrap_from_polygon_tickers (injects fetcher)
├── tiingo_tickers.py        # bootstrap_from_tiingo_tickers (injects fetcher)
├── congress_bioguide.py     # bootstrap_from_congress_bioguide (injects fetcher)
├── gics_sectors.py          # bootstrap_from_gics (reads bundled file)
└── iso_countries.py         # bootstrap_from_iso_countries (reads bundled file)

services/api/data/                      # NEW directory — bundled static registries
├── gics_industries.json     # 150 GICS industries (level 4) + parents
└── iso_3166_countries.json  # 249 ISO country codes

services/api/tests/
├── test_entity_bootstrap_persist.py
├── test_entity_bootstrap_normalize.py
├── test_entity_bootstrap_sec_cik.py
├── test_entity_bootstrap_gleif.py
├── test_entity_bootstrap_polygon_tickers.py
├── test_entity_bootstrap_tiingo_tickers.py
├── test_entity_bootstrap_congress.py
├── test_entity_bootstrap_gics.py
└── test_entity_bootstrap_iso_countries.py
```

## Public API

```python
from app.services.entity_bootstrap import (
    bootstrap_from_sec_cik,
    bootstrap_from_gics,
    bootstrap_from_iso_countries,
    bootstrap_from_gleif,
    bootstrap_from_polygon_tickers,
    bootstrap_from_tiingo_tickers,
    bootstrap_from_congress_bioguide,
    BootstrapError,
)
```

Each function returns `list[BootstrappedEntity]` (from `app/schemas/extraction.py`, contract appended by 3c). Each function takes an `AsyncSession` and writes entities. Functions that depend on 3f clients accept the fetcher as a callable arg (for testability and pre-integration use).

## Idempotency

A bootstrapped entity is uniquely identified by `(type, external_ids.<canonical key>)`. The `_persist.insert_or_get_entity` function:

1. Look up by canonical external_id (e.g., for SEC CIK bootstrap: `entities.external_ids->>'cik' == '0000320193'`).
2. If exists: update aliases (union with existing), return existing.
3. If not exists: insert new with full alias set, confidence=1.0, needs_review=False.

Postgres supports `->` JSON operators natively; SQLite (test env) supports `JSON_EXTRACT`. Implementation uses SQLAlchemy's `JSON` type accessors which work cross-dialect, OR falls back to fetching candidates and filtering in Python (acceptable for bootstrap because the table is small).

## Normalization rules

`_normalize.py` provides:

- `normalize_company_name(name: str) -> str` — strip trailing "Inc."/"Inc"/"Corp."/"Corp"/"Corporation"/"Co."/"Co"/"Ltd."/"Ltd", normalize whitespace, preserve case (canonical_name keeps original casing).
- `normalize_alias_set(*names: str) -> list[str]` — collect aliases, dedupe, normalize whitespace, return sorted list. Always includes the unstripped legal name and the stripped form.

## GICS + ISO bundled data

The two bundled JSON files live under `services/api/data/`. Format:

```json
// gics_industries.json
[
  {
    "gics_code": "10101010",
    "name": "Oil & Gas Drilling",
    "sector": "10",
    "industry_group": "1010",
    "industry": "101010"
  },
  ...
]
```

```json
// iso_3166_countries.json
[
  {"iso_alpha2": "US", "iso_alpha3": "USA", "name": "United States"},
  {"iso_alpha2": "GB", "iso_alpha3": "GBR", "name": "United Kingdom"},
  ...
]
```

Source data must come from authoritative public lists. The plan checks in stub files with 5–10 sample rows each; populating the full lists is a separate operations step (out of scope for the implementer — they just need the loader plus a few sample rows so the tests pass).

## Mock interfaces for 3f-dependent fetchers

For GLEIF / Polygon / Tiingo / Congress bootstrap, 3c defines the fetcher signature it needs:

```python
# bootstrap_from_gleif signature:
async def bootstrap_from_gleif(
    *,
    session: AsyncSession,
    fetcher: Callable[..., Awaitable[list[GleifRecord]]],  # ← 3f wires the real one
    lei_filter: list[str] | None = None,
) -> list[BootstrappedEntity]: ...
```

The `GleifRecord` type is defined inside `app/services/entity_bootstrap/gleif.py` as a Pydantic model describing the minimal fields 3c needs:

```python
class GleifRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    lei: str
    legal_name: str
    other_names: list[str]
    jurisdiction: str  # ISO alpha2
```

When 3f's `fetch_gleif_lei` ships, its response type is converted to `GleifRecord` at the call site (or 3f's response type is made compatible). The same pattern applies to Polygon/Tiingo/Congress.

3c's tests use respx to mock the documented GLEIF/Polygon/Tiingo/Congress endpoints and run the fetcher in-process, even though 3f's actual client doesn't exist yet. The "fetcher" in tests is a thin lambda that hits the mocked endpoint via `httpx.AsyncClient` and parses into `GleifRecord`.

## Test Strategy

- `test_entity_bootstrap_persist.py` — `insert_or_get_entity` round-trip + alias union behavior.
- `test_entity_bootstrap_normalize.py` — name normalization, alias dedup.
- `test_entity_bootstrap_sec_cik.py` — full bootstrap from a small `SecCompanyTickersResponse` fixture; asserts 3 entities created with `cik` + `ticker` external_ids.
- `test_entity_bootstrap_gleif.py` — passes a stub fetcher returning 2 `GleifRecord`s; asserts entities + LEI external_id.
- `test_entity_bootstrap_polygon_tickers.py`, `test_entity_bootstrap_tiingo_tickers.py`, `test_entity_bootstrap_congress.py` — same shape.
- `test_entity_bootstrap_gics.py` — loads bundled JSON, asserts sector entities created with `gics_code`.
- `test_entity_bootstrap_iso_countries.py` — loads bundled JSON, asserts country entities.

Target: ~20–30 new tests.

## Verification Gates

- `pytest`: ≥285 (261 baseline + new).
- `ruff check`: clean.
- `mypy app` strict: clean.

## Risks

| Risk | Mitigation |
|---|---|
| Alias union explosion (e.g., GLEIF returning 20 "other_names" per LEI) | Dedupe + cap at 50 aliases per entity. Drop oldest insertions on overflow. |
| `external_ids` JSON-path query non-portable to SQLite test env | Use SQLAlchemy expressions that cross-dialect; OR fetch by `type` and filter in Python (acceptable since bootstrap runs at setup, not per-request). |
| Concurrent bootstrap calls cause duplicate entities | All inserts inside `async with session.begin()` plus the insert-or-get lookup-first pattern. Idempotent under retry. |
| GICS bundled file becomes stale | Out of scope for v0. Add a refresh task in Phase 4+ if needed. |

## Append to `app/schemas/extraction.py` (Contract 4)

After 3b creates the file, 3c appends:

```python
class BootstrappedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: uuid.UUID
    type: EntityTypeEnum
    canonical_name: str
    aliases: list[str]
    external_ids: dict[str, str]
    source_registry: str
```

And appends `"BootstrappedEntity"` to `__all__`.

## Out of scope (carried forward)

- Periodic refresh / re-bootstrap when registries change.
- Cross-registry deduplication (e.g., the same company appears in SEC + GLEIF + Polygon — for v0, each registry creates an entity; 3e resolution handles consolidation via the merge mechanism in 3f).
- Sector/sub-sector hierarchy relations (out of 3c scope).
- Materialized views over `entities`.
