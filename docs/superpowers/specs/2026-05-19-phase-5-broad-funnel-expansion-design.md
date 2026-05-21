# Phase 5 — Broad Funnel Expansion

**Date:** 2026-05-19
**Branch:** `freddysongg/trading-llm-signals` (continuation; no rename)
**Predecessor:** Phase 4 macro brief MVP (`docs/superpowers/specs/2026-05-18-phase-4-macro-brief-mvp-design.md`)
**Plan reference:** `.context/attachments/plan-v3.md`
**Direction spec:** `.context/attachments/research-funnel-spec.md` §5 (pipeline), §7 (schema), §9 (extraction), §10 (resolution), §11 (hypotheses)

## Goal

Expand `funnel_research` from a single-stage macro brief into a parent-run Stage 2 sector fan-out while addressing Phase 4 carry-overs that block scale: public `scope_payload`, budget/rate hardening under fan-out, LLM-judge verification, theme promotion, hypothesis UI, frontend tests, full GICS hierarchy, and a prompt iteration harness.

A user clicks **Run Macro Brief**, watches the timeline progress through `ingest → digest → synthesize → verify → sector_fanout → consolidate → terminal`, then reads a macro brief view that also lists 1–3 sector briefs with their own cited claims, verifier status, and an optional LLM-judge verdict.

## Non-Goals

- No Stage 3 company thesis fan-out, no Stage 4 portfolio brief.
- No new strategies beyond `funnel_research`. No child `ResearchRun` rows — sector briefs are 1:N rows on the parent run.
- No autonomous scheduling. Every funnel run remains user-initiated.
- No background ranker, no full hypothesis lifecycle (`active → validated/refuted/archived`). Only `proposed → active` is exposed in this phase.
- No swap of the deterministic verifier. The LLM judge is an additional check that runs only after the deterministic verifier passes.
- No full sector constituent coverage. Sector evidence selection uses bounded constituents/proxies; full company coverage is future work.
- No Apache AGE, no Neo4j, no LangChain, no LangSmith.

## Locked Decisions (from plan-v3 and brainstorming)

| # | Decision |
|---|---|
| 1 | One parent `funnel_research` run. No child run rows. No new strategy. |
| 2 | Stage scheme extends to `ingest → digest → synthesize → verify → sector_fanout → consolidate → terminal`. |
| 3 | `sector_briefs` is a new 1:N table keyed by `(run_id, sector_entity_id)`. |
| 4 | Default sector fan-out: top `MAX_SECTOR_DEEP_DIVES = 3` non-neutral sector calls, chosen by conviction (descending), ties broken by sector name. |
| 5 | Bounded concurrency: sector fan-out semaphore = 2; per-run extraction semaphore = 4; budget evaluation serialized via Redis lock. |
| 6 | Redis-backed token bucket rate limiter replaces per-process `RateLimiter`. Local in-memory fallback used in tests when Redis is absent. |
| 7 | LLM judge runs after deterministic verify. If judge flags issues, regen reuses existing cap and includes judge reasons. `JudgeStatus = not_run \| passed \| flagged`. |
| 8 | Sector source failures are warn-level. Skip sector with no evidence. Run fails only if all selected sectors fail or no macro brief can be produced. |
| 9 | Theme promotion runs at consolidate. Normalized theme labels appearing in ≥2 verified/judge-passed macro or sector briefs are resolved as `theme` entities; matching hypotheses receive backfilled `scope_theme_ids`. |
| 10 | Migration `006` adds `sector_briefs` table and judge columns on `macro_briefs`. |
| 11 | Full GICS hierarchy: replace flat seed with `gics_code, name, level, parent_gics_code`. All taxonomy nodes are `EntityType.sector` with `attributes.gics_level`. Stage 1 vocabulary remains the 11 top-level sectors. |
| 12 | Stage 2 sector synthesis emits a `SectorBrief` with `companies: list[SectorCompanyIdea]` ranked by conviction, capped per sector. |
| 13 | `GET /api/research/hypotheses` returns paginated enriched rows. `POST /api/research/hypotheses/{id}/activate` transitions `proposed → active` only. |
| 14 | `scope_payload` is exposed on `ResearchRunSummary`, `ResearchRunDetail`, `ResearchRunPublic`. UI renders funnel runs as `MACRO · US EQUITIES`. |
| 15 | Frontend tests use Vitest + React Testing Library; Playwright is used for one end-to-end smoke on the macro run detail flow. |
| 16 | Prompt iteration harness writes JSONL eval output to `.context/prompt-evals/`; runs are reproducible from checked-in case files. |

## Module Layout

```
services/api/
├── alembic/versions/
│   └── 006_phase5_sector_briefs.py                # NEW migration
├── app/
│   ├── db/
│   │   ├── models_macro.py                         # MODIFIED — judge_status, judge_reasons, judge_call_id
│   │   └── models_sector.py                        # NEW — SectorBrief ORM
│   ├── schemas/
│   │   ├── macro_brief.py                          # MODIFIED — JudgePublic, MacroBriefPublic.judge/sector_briefs
│   │   ├── sector_brief.py                         # NEW — SectorBrief, SectorCompanyIdea, SectorBriefPublic
│   │   ├── runs.py                                 # MODIFIED — scope_payload on summary/detail/public
│   │   └── hypotheses.py                           # NEW — HypothesisPublic + filter/page schemas
│   ├── api/routes/
│   │   ├── macro_briefs.py                         # MODIFIED — returns judge + sector_briefs
│   │   └── hypotheses.py                           # NEW — list + activate routes
│   ├── services/
│   │   ├── budget.py                               # MODIFIED — accept lock injection
│   │   ├── redis_lock.py                           # NEW — async budget lock
│   │   ├── source_clients/
│   │   │   ├── _rate_limit.py                      # MODIFIED — Redis-backed adapter, local fallback
│   │   │   └── polygon.py                          # MODIFIED — aggregates ingestion helper if used by sector
│   │   ├── ingestion/
│   │   │   ├── polygon_aggregates.py               # NEW — bounded aggregate ingestion + chunker
│   │   │   ├── _chunkers.py                        # MODIFIED — polygon aggregate chunker
│   │   │   └── __init__.py                         # MODIFIED — export new ingest_polygon_aggregates
│   │   ├── entity_bootstrap/
│   │   │   ├── gics_sectors.py                     # MODIFIED — hierarchical seed loader
│   │   │   └── ...
│   │   ├── llm/client.py                           # MODIFIED — accept budget lock
│   │   └── strategies/funnel_research/
│   │       ├── core.py                             # MODIFIED — fan-out + consolidate stages
│   │       ├── _persist.py                         # MODIFIED — judge fields
│   │       ├── _judge.py                           # NEW — LLM judge wrapper
│   │       ├── sector/                             # NEW sub-package
│   │       │   ├── __init__.py                     # exports run_sector_fanout
│   │       │   ├── selector.py                     # selects ≤3 sector calls
│   │       │   ├── evidence.py                     # sector evidence fetch+ingest
│   │       │   ├── extraction.py                   # bounded extract_from_chunk orchestration
│   │       │   ├── graph.py                        # candidate entity/relation persistence
│   │       │   ├── prompts.py                      # sector synthesis messages
│   │       │   ├── llm_call.py                     # sector synthesis call wrapper
│   │       │   ├── verifier.py                     # deterministic verifier + judge wiring
│   │       │   └── persist.py                      # sector_briefs writer
│   │       ├── _themes.py                          # NEW — theme normalization + promotion
│   │       └── _eval_harness.py                    # NEW — prompt iteration harness entrypoint
│   └── data/
│       └── gics_industries.json                    # REPLACED — full hierarchical seed
└── tests/
    ├── test_alembic_phase5_round_trip.py
    ├── test_db_models_sector.py
    ├── test_schemas_sector_brief.py
    ├── test_schemas_runs_scope_payload.py
    ├── test_runs_scope_payload_api.py
    ├── test_redis_budget_lock.py
    ├── test_redis_rate_limiter.py
    ├── test_funnel_research_sector_selector.py
    ├── test_funnel_research_sector_evidence.py
    ├── test_funnel_research_sector_extraction.py
    ├── test_funnel_research_sector_graph.py
    ├── test_funnel_research_sector_prompts.py
    ├── test_funnel_research_sector_llm_call.py
    ├── test_funnel_research_sector_verifier.py
    ├── test_funnel_research_sector_persist.py
    ├── test_funnel_research_judge.py
    ├── test_funnel_research_themes.py
    ├── test_funnel_research_core_phase5.py
    ├── test_hypotheses_api.py
    ├── test_eval_harness.py
    ├── test_entity_bootstrap_gics_hierarchy.py
    └── test_ingestion_polygon_aggregates.py

apps/web/
├── app/(app)/research/
│   ├── runs/
│   │   ├── page.tsx                                # MODIFIED — renders MACRO · US EQUITIES for funnel
│   │   └── [id]/
│   │       ├── macro-brief-detail.tsx              # MODIFIED — judge badge + sector brief list
│   │       └── sector-brief-detail.tsx             # NEW — single sector view
│   └── hypotheses/
│       ├── page.tsx                                # NEW — list/filter
│       └── actions.ts                              # NEW — activate
├── components/research/
│   ├── judge-badge.tsx                             # NEW
│   ├── sector-brief-card.tsx                       # NEW
│   └── hypothesis-row.tsx                          # NEW
├── tests/                                          # NEW vitest + RTL
│   ├── run-summary-label.test.tsx
│   ├── macro-brief-detail.test.tsx
│   ├── sector-brief-card.test.tsx
│   └── hypothesis-row.test.tsx
├── e2e/                                            # NEW playwright
│   └── macro-run-detail.spec.ts
└── lib/api/schema.ts                               # REGENERATED
```

## Stage Scheme Extension

```python
STAGE_SCHEMES["funnel_research"] = (
    "ingest",
    "digest",
    "synthesize",
    "verify",
    "sector_fanout",
    "consolidate",
)
```

`terminal` is not a literal in the scheme; existing terminal stage names (`succeeded`, `failed`, `cancelled`) are emitted via the same `_emit_strategy_stage` path. `resolve_stage_position` already maps unknown terminal names to `(total, total)`.

## Data Additions

### Migration `006_phase5_sector_briefs.py`

- Adds `macro_briefs.judge_status TEXT NOT NULL DEFAULT 'not_run'` (CHECK constraint over `not_run|passed|flagged`).
- Adds `macro_briefs.judge_reasons JSONB NULL` (list of strings).
- Adds `macro_briefs.judge_call_id UUID NULL` (FK → `llm_call_logs.id`, ON DELETE SET NULL).
- Adds `sector_briefs` table:
  - `id UUID PK`
  - `run_id UUID NOT NULL` (FK → `research_runs.id`, ON DELETE CASCADE)
  - `sector_entity_id UUID NOT NULL` (FK → `entities.id`, ON DELETE RESTRICT)
  - `direction TEXT NOT NULL` (CHECK in `overweight|underweight|neutral`)
  - `payload JSONB NOT NULL` (typed `SectorBrief` blob)
  - `verifier_status TEXT NOT NULL` (CHECK in `verified|quote_unverified`)
  - `regeneration_count INT NOT NULL DEFAULT 0`
  - `judge_status TEXT NOT NULL DEFAULT 'not_run'`
  - `judge_reasons JSONB NULL`
  - `judge_call_id UUID NULL` (FK → `llm_call_logs.id`)
  - `wall_clock_ms INT NOT NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `UNIQUE (run_id, sector_entity_id)`
  - Index on `(run_id)` for fan-in lookup.
- Reverse migration drops in reverse order.

### Full GICS Hierarchy

`data/gics_industries.json` becomes a list of `{gics_code, name, level, parent_gics_code | null}`. The bootstrap creates one `entities` row per taxonomy node with `type='sector'`, `canonical_name=name`, `attributes={gics_level: int, gics_code: str, parent_gics_code: str | null}`. Top-level rows (`level=1`) remain the Stage 1 allowed vocabulary; the existing 11-sector verifier check is fed from `attributes->>'gics_level' = '1'` rather than a hardcoded list.

### Sector Constituent / Proxy Config

A new `services/api/app/data/sector_constituents.json` maps each GICS top-level sector to:

- `proxy_ticker: str` — sector ETF used for Polygon aggregate evidence (e.g. `XLK` for Information Technology).
- `representative_tickers: list[str]` — bounded (≤5) constituent tickers used for Tiingo news + EDGAR filings.

This is the only sector-side evidence selector for Phase 5. Full constituent coverage is deferred.

## Public Schemas

### `scope_payload` on Run Schemas

Add `scope_payload: dict[str, object] | None = None` to:
- `ResearchRunSummary` (used by `/api/research/runs`)
- `ResearchRunDetail` (used by `/api/research/runs/{id}`)
- `ResearchRunPublic` (used by anywhere returning a single run)

Validation occurs upstream in `CreateResearchRunsRequest`; the public surfaces echo the stored JSON.

### Judge + Sector Brief

```python
class JudgeStatus(StrEnum):
    not_run = "not_run"
    passed = "passed"
    flagged = "flagged"

class JudgePublic(BaseModel):
    status: JudgeStatus
    reasons: list[str]
    call_id: uuid.UUID | None

class SectorCompanyIdea(BaseModel):
    name: str
    ticker: str | None
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]

class SectorBrief(BaseModel):
    sector_entity_id: uuid.UUID
    sector_name: str
    direction: SectorCallDirection
    themes: list[Theme]
    companies: list[SectorCompanyIdea]
    watch_items: list[WatchItem]
    cited_claims: list[CitedClaim]
    confidence: float = Field(ge=0.0, le=1.0)
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)

class SectorBriefPublic(BaseModel):
    brief: SectorBrief
    judge: JudgePublic
```

### `MacroBriefPublic` Extension

```python
class MacroBriefPublic(BaseModel):
    brief: MacroBrief
    judge: JudgePublic
    chunks: list[ChunkLookup]           # already exists; coverage expands to sector cited claims
    sector_briefs: list[SectorBriefPublic]
```

### Hypotheses

```python
class HypothesisPublic(BaseModel):
    id: uuid.UUID
    claim_text: str
    state: Literal["proposed", "active"]
    scope_entity_ids: list[uuid.UUID]
    scope_theme_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]
    source_run_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

class HypothesisListResponse(BaseModel):
    items: list[HypothesisPublic]
    next_cursor: str | None
```

## Behaviour

### Stage Orchestration

`run_macro_brief` is renamed conceptually but the entrypoint stays the same; internal flow becomes:

```
ingest → digest → synthesize → verify (deterministic + judge) →
  persist macro_brief →
  sector_fanout (bounded fan-out, per-sector ingest+extract+graph+synthesize+verify+judge+persist) →
  consolidate (theme promotion + hypothesis backfill) →
  succeeded
```

Stage events are emitted on the parent run only. Per-sector progress is surfaced via run events (`info`-level) with `sector_entity_id` in the event data.

### Stage 2 Sector Fan-out

1. **Select** ≤ `MAX_SECTOR_DEEP_DIVES` (default 3) sector calls from the macro brief, ordered by `(direction != neutral, conviction desc, sector_name asc)`. If <3 non-neutral, take what is available.
2. **Per sector** under `asyncio.Semaphore(2)`:
   - Fetch sector-specific evidence via Tiingo news (representative tickers), Polygon aggregates (proxy ETF), EDGAR filings (≤2 per ticker), Polymarket/Kalshi sector-tagged markets.
   - Ingest into `evidence` + `evidence_chunks` using existing ingestion module; reuse content-hash idempotency.
   - Run `extract_from_chunk` over the sector chunks under per-run `asyncio.Semaphore(4)`. Resolve candidate entities through the existing entity resolution pipeline. Persist relations only when both endpoints resolve.
   - Build sector synthesis messages including macro context, sector digest, and the verified chunk list.
   - Call LLM synthesis with the same `LlmClient` + budget routing.
   - Run deterministic verifier (substring + sector vocabulary + sector-name match).
   - Run LLM judge if deterministic verifier passes. Apply regen with judge reasons up to existing cap.
   - Persist `sector_briefs` row.
3. **Errors**: Per-source ingest failures are warn-level events. A sector with zero ingested chunks is skipped (warn). A sector synthesis LLM failure (non-budget) marks that sector as failed but does not abort the parent run. The parent run fails only if (a) macro brief production failed, or (b) all selected sectors failed.

### LLM Judge

`_judge.run_judge(brief: MacroBrief | SectorBrief, *, llm_complete, run_id, session)`:

- Prompt asks the judge to look for contradictions between cited claims and sector calls or theme directions, claims unsupported by their cited evidence, and sector-call direction reversals.
- Output schema: `{"status": "passed" | "flagged", "reasons": list[str]}`.
- Runs only after the deterministic verifier returns `verified` (skipped otherwise; persisted as `judge_status='not_run'`).
- Counts toward the regen cap when status is `flagged`.

### Theme Promotion

`_themes.promote_themes(*, session, run_id)`:

- Loads the parent macro brief and all `verified` sector briefs for the run.
- Normalizes theme strings to a slug (`lower`, strip, collapse whitespace, ASCII fold).
- Themes present in ≥2 verified/judge-passed briefs are inserted as `entities` rows with `type='theme'`, `canonical_name=display label`, `attributes={normalized_slug}`. Existing matches are reused.
- For each hypothesis in this run whose `claim_text` contains a promoted theme label (case-insensitive), append the new theme entity id to `scope_theme_ids` (deduplicated).

### Redis-Backed Budget Lock

`services/api/app/services/redis_lock.py`:

```python
class BudgetLockProtocol(Protocol):
    async def __aenter__(self) -> "BudgetLockProtocol": ...
    async def __aexit__(self, *_: object) -> None: ...

class RedisBudgetLock(BudgetLockProtocol):
    """Acquires a per-run lock in Redis, with a TTL fallback and exponential backoff."""

class LocalBudgetLock(BudgetLockProtocol):
    """asyncio.Lock-backed in-process fallback for tests and dev without Redis."""
```

`LlmClient._evaluate_and_persist` accepts an optional `lock_factory: Callable[[UUID | None], BudgetLockProtocol]`. The default uses Redis when `settings.redis_url` is set, else `LocalBudgetLock`. The lock is keyed on `run_id` so multiple sector tasks within the same run serialize on budget evaluation while different runs proceed concurrently.

### Redis-Backed Token Bucket

`RateLimiter` is split:

- `RateLimiterProtocol` (existing `acquire()` shape preserved).
- `LocalTokenBucket` — current implementation, used in tests when Redis is unavailable.
- `RedisTokenBucket` — same shape, uses a Lua script `services/api/app/services/source_clients/_rate_limit_redis.lua` for atomic refill+deduct.

Existing module-level singletons stay; their definitions are upgraded to dispatch via `make_rate_limiter(name=..., rate_per_second=..., burst=...)` which picks Redis when configured.

### Workers

`app/workers/tasks.py` is the only place worker-scoped `LlmClient` + `RateLimiter` instances are created. Wire them to the shared limiter/lock by constructing them through factories that honor `settings.redis_url`.

## Hypotheses API

- `GET /api/research/hypotheses`
  - Query params: `state: proposed | active | all (default all)`, `cursor: str | None`, `limit: int (default 25, max 100)`.
  - Returns `HypothesisListResponse` ordered by `created_at desc`.
- `POST /api/research/hypotheses/{id}/activate`
  - Transitions `state: proposed → active`. Returns 409 if not `proposed`. Returns 404 if not found. Emits a `RunEvent` on the source run for traceability.

## Prompt Iteration Harness

`app/services/strategies/funnel_research/_eval_harness.py` is invoked via a small CLI script `services/api/scripts/run_prompt_evals.py`. It:

1. Loads cases from `services/api/prompts/cases/*.json` (each case: `{name, scope, fixture_chunks: list[ChunkRef], expected: PartialBrief}`).
2. Iterates checked-in prompt versions under `app/services/strategies/funnel_research/_prompts.py` exports.
3. For each (case, version): calls a deterministic mocked LLM completion (no live API), records output, computes diff vs. expected.
4. Writes JSONL to `.context/prompt-evals/<utc-timestamp>.jsonl` (one line per (case, version)).
5. CI is opt-in; not run on every build.

The harness is not wired to any worker dispatch; it is a developer tool.

## Frontend

### Vitest + React Testing Library

`apps/web/package.json` gains `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`. Configuration in `apps/web/vitest.config.ts` with path aliasing matching `tsconfig.json`. Test scripts:

- `pnpm --filter web test` → vitest run
- `pnpm --filter web test:watch` → vitest watch

### Playwright

`apps/web/playwright.config.ts` runs against `pnpm --filter web dev` (manual; the user does not start servers from agents). The smoke test asserts the macro run detail flow renders timeline, cited claims, judge badge, and at least one sector brief card when the API returns the canned fixture.

### Runs List Label

For each `ResearchRunSummary` returned by the API where `strategy === "funnel_research"`, the runs list shows `MACRO · US EQUITIES` (uppercase, middle dot separator). `scope_payload.kind === "macro"` is the source of truth.

## Test & Review Gates

Backend gates:
- `pytest -q` green.
- `ruff check`, `mypy app`.
- Alembic round-trip (`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`).

Frontend gates:
- `pnpm --filter web typecheck`, `lint`, `build`.
- `pnpm --filter web test` (new).
- `pnpm --filter web e2e:smoke` (new) — manual sign-off.

Review-agent gates remain per `plan.md`: a review pass after each commit slice (schemas, redis, sector fan-out, surfaces) before moving to the next.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Sector fan-out blows the per-run budget. | Budget lock serializes evaluation; the existing soft/hard/catastrophic guards stay in place. |
| Redis unavailability in dev. | `LocalBudgetLock` and `LocalTokenBucket` are the default when `settings.redis_url` is empty. |
| Judge regressions on valid briefs. | Judge runs only after deterministic verify passes; flagged briefs still persist with the judge status surfaced rather than failing the run. |
| Sector synthesis cost explosion. | Synthesis model pinned (no upgrade path in Phase 5); sector input capped via constituent allowlist + bounded chunk count. |
| Theme over-promotion. | Promotion requires ≥2 verified/judge-passed briefs and normalized slug match. |
| Stage scheme drift in UI. | UI consumes `total_stages` from `stage_event` payloads, not a hardcoded count. |

## Open Questions

None blocking. Sector constituent coverage beyond the bounded seed and Stage 3 company thesis are deferred to a later phase.
