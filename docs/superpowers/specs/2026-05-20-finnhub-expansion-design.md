# Finnhub MVP Expansion — Design Spec

**Date:** 2026-05-20
**Tracker:** User-requested 2026-05-20, scope captured in `.context/handoff-cycles-1-through-4-complete.md` ("Outstanding work → New work — Finnhub data-source expansion").
**Cycle:** Post-Phase-7 new work (not a cleanup item).

## Problem

The funnel-research company fan-out (`services/api/app/services/strategies/funnel_research/company/evidence.py::fetch_company_evidence`) currently fetches four sources per company deep-dive: Polygon aggregates, Tiingo news, Ainvest/Capitol Trades congressional trades, and SEC EDGAR submissions. The Finnhub source-client framework was scaffolded in Phase 3 (`services/api/app/services/source_clients/finnhub.py`) and used for one endpoint (`/company-news`), but four high-value free-tier endpoints remain unwired. As a result:

- Analyst recommendation trends and price targets — direct support/contradict signals for earnings and demand hypotheses — never enter the evidence graph.
- Insider transactions (officer/director Form 4 disclosures) — a higher-fidelity directional signal than congressional STOCK Act disclosures — never enter the graph.
- Sector peer lists — useful for future fan-out candidate expansion when ours is sparse — are unavailable to the system.
- Company profile metadata (country, industry, IPO date, market cap, shares outstanding) — the natural feed for `Entity.attributes` and Item 5's attribute mining — is never harvested.

The Finnhub API key is already in `Settings`, the rate limiter is already named and configured, the data-source registry already seeds `finnhub_news`. What is missing is the per-endpoint wiring.

## Goals (in scope)

- Add five free-tier Finnhub endpoints (`/stock/recommendation`, `/stock/price-target`, `/stock/insider-transactions`, `/stock/peers`, `/stock/profile2`) as additional company-evidence sources.
- Land each as a single-source ingester following the `finnhub_news.py` pattern (not the `congress_trading.py` multi-source orchestrator pattern).
- Backfill `Entity.attributes` from `/stock/profile2` for entities already resolved by ticker, with stable-field/volatile-field discipline.
- Register one `DataSourceSeed` per endpoint with calibrated reliability scores so the belief engine weights evidence correctly.
- Preserve the existing per-source warn-on-failure isolation in `fetch_company_evidence`.

## Non-goals

- Premium / paid-tier endpoints (transcripts, news-sentiment aggregates, insider-sentiment scores). Defer.
- Real-time WebSocket subscriptions. The funnel runs on a per-run cadence; streaming is future live-trading work.
- Selector-level candidate expansion from `/stock/peers`. The chunks landed here are the future-enabling raw material, but the selector hook (pre-fan-out peer expansion, peer-score, expansion cap) is a separate brainstorm.
- Forex / crypto / non-US-equity feeds. Out of desk scope.
- Creating new `Entity` rows from profile data. Profile backfill only updates entities that already exist (resolved by ticker). Entity creation stays inside the entity-resolution pipeline.

## Architecture decisions

### Decision 1 — Module pattern: `finnhub_news.py`, not `congress_trading.py`

`congress_trading.py` is a multi-source orchestrator (Ainvest primary, Capitol Trades fallback, normalised `CongressTrade` dataclass). Each Finnhub endpoint is single-source — there is no fallback, no normalisation across providers. Using the orchestrator pattern would be over-engineering. The shape that fits is `finnhub_news.py`:

- A module-level `_SOURCE = "finnhub_<endpoint>"` constant.
- A `_document_id(...)` deterministic helper for idempotency.
- A `_count_chunks(...)` helper for the already-ingested branch.
- The public `ingest_finnhub_<endpoint>(*, session, payload, content_hash, raw_url) -> IngestedEvidence`.

Response Pydantic models live alongside `FinnhubNewsItem` in `services/api/app/services/source_clients/finnhub.py`. Fetch functions live in the same source-client module. This keeps source-client wire-format concerns isolated from ingestion / chunking concerns.

Rejected alternatives:

- **Co-locating each fetcher under `strategies/funnel_research/company/`.** Couples source-client knowledge into the strategy layer. The current split (source-client → ingester → strategy) is what `finnhub_news` already follows.
- **Single `finnhub.py` ingester with a dispatcher.** Forces the per-endpoint chunking + document-id logic into one file that would grow uncomfortably large. The `finnhub_news.py` per-endpoint module is the established precedent.

### Decision 2 — Chunking strategy per endpoint

| Endpoint | Granularity | Rationale |
|----------|-------------|-----------|
| `/stock/recommendation` | One chunk per monthly period | API returns a list of monthly snapshots, each a distinct point-in-time aggregate. Per-period chunks let the belief engine attribute time-decay to individual observations. |
| `/stock/price-target` | One chunk (single object) | API returns one aggregate row (median/mean/high/low + analyst count + last-updated). Splitting would fragment a single point-in-time snapshot. |
| `/stock/insider-transactions` | One chunk per transaction | Analogous to `congress_trading.chunk_congress_trades` — each Form 4 row is an independent disclosure. |
| `/stock/peers` | One chunk (peer list) | The list IS the document; per-peer chunks would create N chunks that all say "X is a peer of Y" with no extra signal. |
| `/stock/profile2` | One chunk | Single company-profile snapshot; per-field chunks would fragment. |

All chunkers live co-located with their ingester. `ingestion/_chunkers.py` is already crowded and these are trivial functions — no benefit to centralising.

### Decision 3 — Reliability scores

Calibrated against existing seeds (`sec_edgar=0.95`, `ainvest_congress=0.8`, `capitol_trades=0.75`, `tiingo_news=0.85`, `finnhub_news=0.7`, `gdelt=0.4`):

| name | kind | reliability_score | reasoning |
|------|------|-------------------|-----------|
| `finnhub_recommendation` | `analyst` | 0.75 | Aggregate of trained-professional opinions. Structurally clean numbers, but the underlying signal is opinion. Tier between paid news (0.85) and free news aggregator (0.7). |
| `finnhub_price_target` | `analyst` | 0.75 | Same tier; mechanically derived from the same analyst pool. |
| `finnhub_insider_transactions` | `trading_disclosures` | 0.85 | SEC Form 4 disclosures relayed through Finnhub. Form 4s are legally mandated within two business days, stricter than STOCK Act → higher than `ainvest_congress` (0.8) but below `sec_edgar` (0.95) to account for the aggregator layer. |
| `finnhub_peers` | `entity_registry` | 0.65 | Algorithmically computed metadata, useful for entity expansion / context but low decision weight on its own. Below `openfigi` (0.95) and `gleif` (0.95) because those are official registries; this is heuristic. |
| `finnhub_profile` | `entity_registry` | 0.85 | Regulatory-sourced company metadata (country, industry, IPO date). High fidelity; parity with paid structured news. |

One new `kind` value (`analyst`) joins the existing taxonomy. `entity_registry` is reused for peers + profile (both metadata about entities).

### Decision 4 — Profile2 entity-attribute backfill: stable / volatile split

Profile data lands as evidence chunks **and** updates `Entity.attributes` for ticker-resolved entities. This unblocks Item 5 (attribute mining) — the miner sees structured data directly rather than text-parsing chunks — and enables future entity comparisons (peer screening, attribute drift).

To avoid churn, fields are split:

- **Stable → `Entity.attributes` (set-if-missing-or-changed):** `country`, `currency`, `exchange`, `ipo_date`, `weburl`, `finnhub_industry`. The backfill never touches `Entity.canonical_name`, `Entity.aliases`, or `Entity.external_ids` — those are the entity-resolver's invariants.
- **Volatile → chunks only:** `marketCapitalization`, `shareOutstanding`. These move and we want a time-series via evidence, not entity-attribute churn.
- **All fields → chunks:** Provenance + time-series for every column, regardless of which subset feeds `Entity.attributes`.

Constraints:

- **Only update existing entities** (lookup via `Entity.ticker_normalized` matching the run's company ticker, case-folded). If no entity row exists for the ticker, skip the attribute backfill silently — entity creation is the entity-resolution pipeline's job and routing around it would bypass the review queue (Item 6).
- **Last-writer-wins** on concurrent updates. Sweep is rare per ticker (one profile fetch per company per run); the two-worker race is theoretical and converges to the same final state.
- **No version history on `Entity.attributes`.** Time-series lives in the evidence chunks. If audit history becomes a requirement, an `entity_attribute_history` table is the right abstraction — out of scope here.

Rejected alternatives:

- **Full `Entity.attributes` replace on every ingest.** Triggers churn for transient field changes (e.g., Finnhub flipping classification format) and obscures whether the value came from Finnhub or another source. Set-if-missing-or-changed at the field level is finer-grained.
- **Versioned attributes per source.** Premature; no concrete consumer yet. Re-evaluate when Item 5 ships if attribute provenance becomes a need.

### Decision 5 — Peers chunk structure: data-discipline now, selector wiring later

The chunks land peers as `attributes={"peers": ["MSFT", "GOOGL", "AMZN"], "for_ticker": "AAPL"}` (structured list). The chunk text is human-readable (`"Finnhub peers for AAPL: MSFT, GOOGL, AMZN"`). When a future selector-expansion design is built, it can JSON-query `EvidenceChunk.attributes->'peers'` directly without re-parsing text.

Out of scope: the selector itself. That requires a pre-fan-out hook, peer-score / inclusion-rule, expansion cap, and ordering changes — a separate brainstorm.

### Decision 6 — Date windows: 90-day inline constants

Two endpoints take date ranges:

- `/stock/insider-transactions` — lookback constant `_INSIDER_LOOKBACK_DAYS = 90`. Form 4 filings can be retroactive within a window; 90 days catches transactions filed during the current quarter plus the previous quarter's straggler filings.
- `/stock/recommendation` — Finnhub returns up to four months of monthly snapshots regardless of the requested window; no lookback constant needed.

No new `Settings` field. The Finnhub API key already exists; date windows are mechanical and tied to data semantics, not ops tuning.

### Decision 7 — Free-tier verification: trust handoff, isolate at runtime

The handoff classified priorities 1–5 as free-tier based on prior knowledge. The next chat does not run a separate verification pass — the existing per-source warn-on-failure path in `fetch_company_evidence` already handles unexpected 4xx responses gracefully. If during exercise one endpoint returns 403 (premium-tier gating change), the evidence path warns and continues, and ops gets a signal to either drop the endpoint or upgrade the tier.

This trades a small risk of warn-event noise on first deployment for not building a one-shot verification script that ops would then have to re-run quarterly.

## Components

### New files

| Path | Responsibility |
|------|----------------|
| `services/api/app/services/ingestion/finnhub_recommendation.py` | Ingester + chunker for `/stock/recommendation`. |
| `services/api/app/services/ingestion/finnhub_price_target.py` | Ingester + chunker for `/stock/price-target`. |
| `services/api/app/services/ingestion/finnhub_insider_transactions.py` | Ingester + chunker for `/stock/insider-transactions`. |
| `services/api/app/services/ingestion/finnhub_peers.py` | Ingester + chunker for `/stock/peers`. |
| `services/api/app/services/ingestion/finnhub_profile.py` | Ingester + chunker for `/stock/profile2`, plus the `Entity.attributes` backfill helper. |
| `services/api/tests/test_finnhub_recommendation.py` | Source-client + ingestion + idempotency. |
| `services/api/tests/test_finnhub_price_target.py` | Source-client + ingestion + idempotency. |
| `services/api/tests/test_finnhub_insider_transactions.py` | Source-client + ingestion + idempotency. |
| `services/api/tests/test_finnhub_peers.py` | Source-client + ingestion + idempotency. |
| `services/api/tests/test_finnhub_profile.py` | Source-client + ingestion + idempotency + `Entity.attributes` backfill paths. |

### Modified files

| Path | Change |
|------|--------|
| `services/api/app/services/source_clients/finnhub.py` | Add response Pydantic models (`FinnhubRecommendation`, `FinnhubPriceTarget`, `FinnhubInsiderTransaction`, `FinnhubPeers`, `FinnhubCompanyProfile`) + fetch functions (`fetch_finnhub_recommendation`, `fetch_finnhub_price_target`, `fetch_finnhub_insider_transactions`, `fetch_finnhub_peers`, `fetch_finnhub_profile`). |
| `services/api/app/services/data_sources_bootstrap/registry.py` | Append five `DataSourceSeed` rows per Decision 3. |
| `services/api/app/services/strategies/funnel_research/company/evidence.py` | Extend `CompanySourceFetcher` with five new callable fields; extend `default_company_fetcher()`; add five `_fetch_X` helpers mirroring `_fetch_news` / `_fetch_congress_trades`; insert calls into `fetch_company_evidence()` after the existing four. |
| `services/api/tests/test_company_evidence.py` | Add fan-out integration tests asserting the five new sources land in `IngestedEvidence` and per-source failures stay isolated. |
| `services/api/tests/test_data_sources_bootstrap.py` | Update count assertions if any (the bootstrap iterates `KNOWN_DATA_SOURCES`, so the existing tests should pass automatically; if a hard count is asserted somewhere, bump it). |

## Data flow

For a single company `C` with ticker `T` in the funnel-research fan-out:

1. `fetch_company_evidence` opens an HTTP client and dispatches per-source calls (existing four + five new).
2. Each new Finnhub fetcher:
   - Calls `fetch_finnhub_<endpoint>(client, T, ...)` in the source-client module, with `_rate_limiter()` shared across all Finnhub endpoints (the existing rate-limiter name `finnhub` covers them).
   - Returns `(typed_payload, content_hash)`.
3. The matching `_fetch_<endpoint>` helper in `evidence.py`:
   - Emits a `_warn` and returns `None` on exception.
   - Returns `None` if the payload is empty (e.g., zero recommendation rows).
   - Otherwise calls `ingest_finnhub_<endpoint>(session=..., payload=..., content_hash=..., raw_url=None)`.
4. The ingester:
   - Computes `_document_id(...)` deterministically.
   - `insert_or_get_evidence(...)` — idempotent on `(source, document_id)`.
   - If newly inserted: chunk via the co-located chunker, `insert_chunks(...)`, return `IngestedEvidence(chunk_count=...)`.
   - If already present: `_count_chunks(...)`, return `IngestedEvidence(chunk_count=existing)`.
5. **Profile-only addendum:** after the chunk write, `ingest_finnhub_profile` calls `_backfill_entity_attributes(session, ticker=T, payload=...)` which:
   - Looks up `Entity` by `ticker_normalized == T.upper()`. If none, return.
   - For each stable field, `set_if_missing_or_changed` on `Entity.attributes`.
   - Flushes; the outer `session.commit()` in `fetch_company_evidence` finalises.
6. `fetch_company_evidence` commits between each source (existing pattern) so a downstream failure can't roll back upstream work.
7. The chunk refs are loaded as before and returned to the orchestrator.

## Wire formats (Finnhub free-tier reference)

Captured here for the implementer; verify against `https://finnhub.io/docs/api` during execution and adjust Pydantic models accordingly. `extra="ignore"` on all models tolerates upstream additions.

- **`/stock/recommendation?symbol=...`**: returns a JSON array of `{symbol, period (YYYY-MM-DD), buy, hold, sell, strongBuy, strongSell}`.
- **`/stock/price-target?symbol=...`**: returns `{symbol, lastUpdated, targetHigh, targetLow, targetMean, targetMedian, numberOfAnalysts}`.
- **`/stock/insider-transactions?symbol=...&from=YYYY-MM-DD&to=YYYY-MM-DD`**: returns `{symbol, data: [{name, share, change, filingDate, transactionDate, transactionCode, transactionPrice}]}`.
- **`/stock/peers?symbol=...`**: returns a JSON array of ticker strings.
- **`/stock/profile2?symbol=...`**: returns `{country, currency, exchange, finnhubIndustry, ipo (YYYY-MM-DD), logo, marketCapitalization, name, phone, shareOutstanding, ticker, weburl}`.

## Testing

Each endpoint gets a sibling test module at `services/api/tests/test_finnhub_<endpoint>.py` with three tests:

1. **Source-client test.** Uses `httpx.MockTransport` to stub the upstream JSON. Asserts the Pydantic model parses, the content hash is stable, and the rate limiter is invoked (via a fake limiter).
2. **Ingestion happy-path.** Builds a typed payload, calls `ingest_finnhub_<endpoint>(...)`, asserts `IngestedEvidence` carries `_SOURCE`, the expected `chunk_count`, and a sampled chunk's text + attributes look right.
3. **Re-ingest idempotency.** Same payload + same content hash on a second call yields zero new chunks (matched by `_count_chunks`).

`test_finnhub_profile.py` gets four additional tests:

4. **Backfill — entity exists, attributes empty:** stable fields populated, volatile fields skipped.
5. **Backfill — entity exists, attribute already set:** non-changed values left untouched; changed values overwritten.
6. **Backfill — no entity row for ticker:** silently returns; no row created.
7. **Backfill — concurrent-style update via two ingests:** last-write wins on overlapping fields.

`tests/test_company_evidence.py` gets two fan-out integration tests:

8. **All five new sources contribute evidence** under happy-path mocks.
9. **One failed Finnhub source warns and the other four still ingest** (per-source isolation invariant).

Expected total: **5 × 3 + 4 + 2 = 21 new backend tests.** No new web tests.

## Rollout

- No migration required. `Entity.attributes` is already a JSON column; the schema is unchanged. `data_sources` row inserts are idempotent via the existing bootstrap helper.
- OpenAPI / web schema regeneration: not required. No new HTTP endpoints. No new fields on existing response schemas.
- Backfill of historical runs: not required. New sources start contributing on the next funnel run after deploy.
- Operational handle: the existing per-source warn-on-failure path means a misconfigured Finnhub key surfaces as five warn events per company. Ops can grep the worker logs for `finnhub` to confirm health post-deploy.

## Risks

- **Rate-limit collision across five endpoints sharing the `finnhub` limiter.** At 1 rps with burst 5, a single company hits 5 Finnhub endpoints sequentially in ~5 seconds. For a 10-company run, that's 50 calls / 50 seconds — well inside operational bounds. If a future run expands fan-out beyond ~30 companies, the limiter may begin throttling. Mitigation: re-evaluate the limiter config (or parallelise across companies with a semaphore) at that time.
- **Profile2 industry classification drift.** Finnhub uses its own `finnhubIndustry` taxonomy, which may not align with GICS or other industry classifications already in `Entity.attributes`. Mitigation: namespace the attribute key as `finnhub_industry` (not `industry`) — already reflected in Decision 4 — so a future GICS feed coexists without collision.
- **Insider transaction signal-to-noise.** Form 4 disclosures include programmatic 10b5-1 sales which carry low informational content. The belief engine relies on extraction-stage attribute parsing to filter; for v0 we rely on the extractor's text-level understanding. A future filter on `transactionCode` (e.g., suppressing `S` sales filed under 10b5-1) is a follow-up.
- **Peers list staleness.** Finnhub's peer algorithm may include de-listed or M&A'd tickers. We do not deduplicate against the run's known company set. Mitigation: leave the dedup to the future selector-expansion design.
