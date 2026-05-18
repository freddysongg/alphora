# Phase 3f — Remaining 8 Source Clients + Entity Merge Mechanism

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-3f-clients-and-merge` (off `origin/freddysongg/trading-llm-signals` @ `cbf3982`)
**Parallel coordination:** `docs/superpowers/phase-3-parallel-coordination.md`
**Spec sections:** `.context/attachments/research-funnel-spec.md` §10 (merge mechanism), Section X (data sources)
**Plan reference:** `.context/attachments/plan.md` Phase 3 items 1 (clients), 5 (merge mechanism)

## Goal

Two complementary deliverables:

1. **8 remaining source clients** on Phase 3a's foundation: Polygon, Tiingo, Ainvest, Kalshi, Congress.gov, Polymarket, OpenFIGI, GLEIF. Each follows the exact template established by `app/services/source_clients/fred.py` and `sec_edgar.py` from Phase 3a.

2. **Entity merge mechanism** that takes an `EntityMergeCommand` and atomically rewires relations + flips tombstone pointer + records the merge.

This phase is the largest in 3b–3f. It is structured as 9 independent task groups that share a single branch but commit separately.

## Non-Goals

- No real-time data subscriptions (REST polling only).
- No order-placement APIs (Polymarket, Kalshi market access is read-only).
- No new entity-resolution logic (3e owns that).
- No new migrations unless `entity_merge` needs an index for performance (discretionary).
- No new schema for any client response (use `extra="ignore"`).
- No Kalshi WebSocket integration.
- No Congress.gov bill body / amendment text — only the structured metadata endpoints.
- No backfill scripts. Caller is responsible for invoking each fetcher.

## Sub-deliverable 1 — 8 source clients

Each client follows the **canonical template** from Phase 3a:

```python
# app/services/source_clients/<provider>.py

_RATE_LIMITER = RateLimiter(rate_per_second=X, burst=Y)


class ProviderResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    # ... typed fields ...


async def fetch_xxx(
    *, client: httpx.AsyncClient, <provider-specific kwargs>,
) -> tuple[ProviderResponseModel, str]:
    ...
```

Settings additions in `app/config.py` for keyed providers:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    # Phase 3f additions
    polygon_api_key: SecretStr | None = None
    tiingo_api_key: SecretStr | None = None
    ainvest_api_key: SecretStr | None = None
    kalshi_api_key_id: SecretStr | None = None
    kalshi_api_key: SecretStr | None = None
    congress_api_key: SecretStr | None = None
    openfigi_api_key: SecretStr | None = None
    # GLEIF, Polymarket — public, no keys
```

Per-client scope is intentionally **narrow** — one or two endpoints each, chosen to be the minimum useful surface for Phase 4 / 5. We are not building exhaustive client libraries.

| Provider | Endpoint(s) | Rate limit | Public function(s) |
|---|---|---|---|
| **Polygon** | `/v3/reference/tickers` (tickers list); `/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}` (aggregates) | 5 rps free tier | `fetch_polygon_tickers`, `fetch_polygon_aggregates` |
| **Tiingo** | `/iex/{ticker}` (latest); `/tiingo/daily/{ticker}/prices` (history) | depends on plan; default 60 req/hour | `fetch_tiingo_latest`, `fetch_tiingo_daily_prices` |
| **Ainvest** | `/api/congress/transactions` (congress trades feed) | ~5 rps | `fetch_ainvest_congress_transactions` |
| **Kalshi** | `/trade-api/v2/markets` (markets index); `/trade-api/v2/markets/{ticker}` (market detail) | 10 rps | `fetch_kalshi_markets`, `fetch_kalshi_market_detail` |
| **Congress.gov** | `/v3/bill?api_key=...` (bills); `/v3/member?api_key=...` (members) | 5,000 req/hr | `fetch_congress_bills`, `fetch_congress_members` |
| **Polymarket** | `https://gamma-api.polymarket.com/events` (events index); `https://gamma-api.polymarket.com/markets` (markets) | unspecified — be conservative at 5 rps | `fetch_polymarket_events`, `fetch_polymarket_markets` |
| **OpenFIGI** | `https://api.openfigi.com/v3/mapping` (POST batch identity mapping) | 25 req/min unauth, 250 req/min keyed | `fetch_openfigi_mapping` |
| **GLEIF** | `https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=...` (search); `/v1/lei-records/{lei}` (by LEI) | unspecified; be conservative at 5 rps | `fetch_gleif_search`, `fetch_gleif_by_lei` |

Each client gets a separate test file with respx-mocked happy path + at least one error path (403 / 429 / 400 as appropriate).

Auth notes:
- **Polygon**: `apiKey` query param.
- **Tiingo**: `Token <key>` Authorization header (or `?token=`).
- **Ainvest**: vendor-specific (consult docs at impl time; default to API key header `X-API-KEY` and fall back to query param if 401).
- **Kalshi**: 2-part auth (`KALSHI_API_KEY_ID` + private-key signing for `/portfolio` endpoints; for `/markets` endpoints, header `KALSHI-ACCESS-KEY: <id>` suffices for v0). Read-only endpoints in 3f don't need the full signing flow.
- **Congress.gov**: `api_key` query param.
- **OpenFIGI**: `X-OPENFIGI-APIKEY` header (optional).
- **Polymarket**: no auth on Gamma API.
- **GLEIF**: no auth.

## Sub-deliverable 2 — Entity merge mechanism

Per spec §10 merge mechanism. When two entities are discovered to be one:

```python
# app/services/entity_merge/__init__.py public API

async def merge_entities(
    *, session: AsyncSession, command: EntityMergeCommand,
) -> EntityMergeRecord:
    """Atomically merge `merged_id` into `surviving_id`.

    Effects within one transaction:
      1. Update all relations.from_id == merged_id → surviving_id.
      2. Update all relations.to_id == merged_id → surviving_id.
      3. Set entities.merged_into_id = surviving_id on the merged row.
      4. Union aliases: surviving.aliases ∪= merged.aliases.
      5. Union external_ids: surviving.external_ids ∪= merged.external_ids (surviving wins on key conflict).
      6. Insert entity_merges row with reason, merged_by, reversible_until=now+30days.
      7. Insert audit_log row with action=merge.

    Raises:
      EntityMergeError if surviving_id == merged_id, or either is already a tombstone.
    """
```

Reversible window: 30 days. Reversal is a separate function `unmerge_entities` that is OUT OF SCOPE for v0 (reversal is rare and manual; can be done via SQL until UI exists).

## Module Layout

```
services/api/app/services/source_clients/
├── __init__.py                 # MODIFIED — 16 new re-exports across 8 clients
├── polygon.py                  # NEW
├── tiingo.py                   # NEW
├── ainvest.py                  # NEW
├── kalshi.py                   # NEW
├── congress_gov.py             # NEW
├── polymarket.py               # NEW
├── openfigi.py                 # NEW
└── gleif.py                    # NEW

services/api/app/services/entity_merge/
├── __init__.py                 # public merge_entities, EntityMergeError, EntityMergeRecord
└── core.py                     # implementation

services/api/app/
├── config.py                   # MODIFIED — 7 new settings
└── schemas/extraction.py       # APPEND EntityMergeCommand (Contract 5)

services/api/tests/
├── test_source_clients_polygon.py
├── test_source_clients_tiingo.py
├── test_source_clients_ainvest.py
├── test_source_clients_kalshi.py
├── test_source_clients_congress_gov.py
├── test_source_clients_polymarket.py
├── test_source_clients_openfigi.py
├── test_source_clients_gleif.py
└── test_entity_merge.py
```

## Contract type appended to `app/schemas/extraction.py` (Contract 5)

```python
class EntityMergeCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str
    merged_by: str
    reversible_until: datetime | None  # defaults to now + 30 days at execution time
```

Add `"EntityMergeCommand"` to `__all__` alphabetically.

## Verification Gates

- `pytest`: ≥325 (261 baseline + ~65 new across 8 clients + merge).
- `ruff check`: clean.
- `mypy app` strict: clean.
- alembic round-trip: clean (no new migration in v0).

## Risks

| Risk | Mitigation |
|---|---|
| 8 clients × per-client edge cases = lots of variation | Stick to the canonical template; deviate only where the provider response shape forces it (just like SEC EDGAR needed model_validators in Phase 3a). |
| Rate-limit math drift across providers | Conservative defaults below documented limits. Same as Phase 3a's discipline. |
| Process-local rate limiter under multi-worker uvicorn | Out of scope for v0 — flagged in coordination doc as deferred. |
| Multi-step Kalshi auth | Skip the auth flow at v0 — endpoints used are read-only and only require the access key. |
| Polymarket Gamma + Data split | Phase 3f covers Gamma only. Data API deferred to Phase 5. |
| `merge_entities` race with concurrent extraction trying to attach a new relation to `merged_id` | At v0, accept eventual consistency: the new relation goes to the merged_id, and a periodic sweep (out of scope) repoints it. Document. |
| OpenFIGI POST body is a batch (up to 100 ids) | Client accepts a list[OpenFigiQuery]; tests cover single + batch. |

## Out of scope (carried forward)

- Polygon WebSocket streams.
- Tiingo IEX live data.
- Kalshi private endpoints (portfolio, orders).
- Polymarket Data API (prices/volumes/trades) — Phase 5.
- Congress.gov bill text / vote details.
- GLEIF relationship records.
- Reversal of entity merges.
- Per-provider response-shape integration tests against live APIs (fixture-based only).
