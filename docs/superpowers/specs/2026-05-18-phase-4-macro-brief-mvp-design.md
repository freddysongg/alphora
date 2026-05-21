# Phase 4 — `funnel_research` Macro Brief MVP

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-4-macro-brief` (off `freddysongg/trading-llm-signals` @ `1ed3b0d`)
**Predecessor handoff:** `.context/attachments/phase-4-brainstorming-handoff.md`
**Plan reference:** `.context/attachments/plan.md` Phase 4 ("Macro Brief MVP")
**Direction spec:** `.context/attachments/research-funnel-spec.md` §5 (pipeline), §7 (schema), §9 (extraction), §10 (resolution), §11 (hypotheses), §13 (model tiering)
**Phase 3 carry-over:** `.context/attachments/phase-3-handoff-v1.md` "Next Up — Phase 4 Macro Brief MVP"

## Goal

Wire the `funnel_research` strategy end-to-end so a user can click **Run Macro Brief** in the UI, watch a four-stage timeline (`ingest → digest → synthesize → verify`), and read a typed `MacroBrief` with themes, sector calls, watch items, cited claims with evidence traceback, a deterministic verifier status, and proposed hypotheses persisted to the existing `hypotheses` table.

This is the first end-to-end caller of the Phase 3 substrate. Stage 1 of the funnel spec emits exactly one LLM synthesis call per run; per-chunk extraction (`extract_from_chunk`) is not invoked from this strategy and remains deferred to Phase 5.

## Non-Goals

- No Stage 2 sector fan-out, no per-chunk LLM extraction, no entity resolution for themes (all deferred to Phase 5).
- No new LLM-powered verifier — the verifier is a deterministic substring check (zero extra LLM cost).
- No promotion of theme strings to first-class `entities` rows.
- No theming of sectors beyond the 11 GICS top-level sector names.
- No new entity-merge invocations from Phase 4's synthesis path.
- No background scheduled funnel runs — every run is user-initiated.
- No advisory locks around GICS bootstrap; rely on Phase 3c's existing `IntegrityError`-catch race handling.
- No frontend test runner. `apps/web/package.json` ships no jest/vitest/playwright; manual verification + `lint`/`typecheck`/`build` only.
- No prompt iteration framework. One v1 prompt template (`macro-brief-v1`).
- No global-equity universe. `MacroBriefScope.universe` is the single-value literal `"us_equities"` for the MVP.

## Module Layout

```
services/api/
├── alembic/versions/
│   └── 005_phase4_macro_brief.py                      # NEW migration: nullable ticker, scope_payload, macro_briefs
├── app/
│   ├── config.py                                      # UNCHANGED (tiingo_api_key already wired in Phase 3)
│   ├── db/
│   │   └── models_macro.py                            # NEW — MacroBrief ORM model
│   ├── schemas/
│   │   ├── macro_brief.py                             # NEW — typed MacroBrief + sub-schemas + MacroBriefScope
│   │   └── runs.py                                    # MODIFIED — funnel_research branch on CreateResearchRunsRequest
│   ├── services/
│   │   ├── entity_bootstrap/
│   │   │   └── gics_sectors.py                        # UNCHANGED entrypoint; consumes expanded JSON
│   │   ├── ingestion/
│   │   │   ├── __init__.py                            # MODIFIED — export 4 new ingest_* + 1 chunker each
│   │   │   ├── _chunkers.py                           # EXTENDED — 4 new chunkers
│   │   │   ├── polymarket_events.py                   # NEW — ingest_polymarket_events
│   │   │   ├── kalshi_markets.py                      # NEW — ingest_kalshi_markets
│   │   │   ├── congress_bills.py                      # NEW — ingest_congress_bills
│   │   │   └── tiingo_news_items.py                   # NEW — ingest_tiingo_news_items
│   │   ├── llm/                                       # UNCHANGED
│   │   ├── run_events.py                              # UNCHANGED
│   │   ├── run_orchestrator.py                        # REFACTORED — strategy-aware StageScheme registry
│   │   ├── source_clients/
│   │   │   ├── __init__.py                            # MODIFIED — export TiingoNews* + fetch_tiingo_news
│   │   │   └── tiingo_news.py                         # NEW — separate from tiingo.py; reuses tiingo_api_key
│   │   └── strategies/                                # NEW package
│   │       ├── __init__.py
│   │       └── funnel_research/
│   │           ├── __init__.py                        # exports run_macro_brief, FunnelResearchError
│   │           ├── config.py                          # SYNTHESIS_MODEL, MAX_REGENERATIONS, PROMPT_VERSION, FRED_SERIES
│   │           ├── _bootstrap.py                      # idempotent GICS sector bootstrap wrapper
│   │           ├── _ingest.py                         # parallel source fetch + ingest -> list[IngestedEvidence]
│   │           ├── _digest.py                         # deterministic per-source Digest model
│   │           ├── _prompts.py                        # build_synthesis_messages
│   │           ├── _llm_call.py                       # synthesis LlmClient wrapper, budget routing
│   │           ├── _verifier.py                       # substring verifier + sector allowlist
│   │           ├── _hypotheses.py                     # ProposedHypothesis -> Hypothesis row writer
│   │           ├── _persist.py                        # macro_briefs row writer + final SSE emission
│   │           └── core.py                            # run_macro_brief(*, session, run_id) — stage orchestrator
│   ├── api/routes/
│   │   ├── research_runs.py                           # MODIFIED — funnel_research branch on POST
│   │   └── macro_briefs.py                            # NEW — GET /research-runs/{id}/macro-brief
│   ├── workers/
│   │   └── tasks.py                                   # MODIFIED — strategy dispatch
│   └── data/
│       └── gics_industries.json                       # REPLACED — 11 GICS top-level sectors
└── tests/
    ├── test_alembic_phase4_round_trip.py              # NEW — migration round trip
    ├── test_db_models_macro.py                        # NEW — ORM model contract
    ├── test_schemas_macro_brief.py                    # NEW — typed schemas + validators
    ├── test_run_orchestrator_stage_scheme.py          # NEW — scheme registry
    ├── test_source_clients_tiingo_news.py             # NEW — respx mock
    ├── test_ingestion_polymarket_events.py            # NEW — respx + DB round trip
    ├── test_ingestion_kalshi_markets.py               # NEW
    ├── test_ingestion_congress_bills.py               # NEW
    ├── test_ingestion_tiingo_news_items.py            # NEW
    ├── test_funnel_research_digest.py                 # NEW — deterministic digest snapshots
    ├── test_funnel_research_prompts.py                # NEW — prompt structure + positional redundancy
    ├── test_funnel_research_verifier.py               # NEW — substring + sector allowlist + regen cap
    ├── test_funnel_research_llm_call.py               # NEW — budget pause/kill wiring
    ├── test_funnel_research_hypotheses.py             # NEW — proposed → Hypothesis row writer
    ├── test_funnel_research_persist.py                # NEW — macro_briefs writer + final SSE
    ├── test_funnel_research_core.py                   # NEW — end-to-end with mocked LLM + respx
    ├── test_research_runs_funnel_post.py              # NEW — POST funnel branch validation
    ├── test_research_runs_macro_brief_get.py          # NEW — GET typed response + 404 paths
    └── test_entity_bootstrap_gics.py                  # MODIFIED — expand assertions to 11 sectors
```

Why a new `strategies/` sub-package: `app/services/` is already busy (12+ flat modules). Strategies live behind one entrypoint per strategy; this is the first one. The TradingAgents path remains in `app/trading_agents/` and `RunOrchestrator.execute`; nothing about that wiring moves.

Why leading underscores on the funnel internals: only `run_macro_brief` and `FunnelResearchError` are public — they are imported by `workers/tasks.py`. Everything else is internal to the strategy.

## Decisions Inherited From Brainstorming

Locked-in decisions (do not relitigate during planning):

| # | Decision |
|---|---|
| 1 | UI-driven end-to-end scope: button → backend run → typed brief view with stage timeline + cost meter + verifier badge. |
| 2 | Tiingo News is a separate `tiingo_news.py` source-client module; auth reuses existing `tiingo_api_key` setting. |
| 3 | Stage 1 synthesis input is raw chunks plus deterministic per-source digests — `extract_from_chunk` is not called. |
| 4 | `research_runs.ticker` becomes nullable; new `scope_payload JSON` column; `POST /research-runs` gains a `funnel_research` branch keyed by `scope_payload`, no `tickers`. |
| 5 | Verifier is deterministic substring + sector-allowlist; regeneration cap at 2; after that persist with `verifier_status="quote_unverified"`. |
| 6 | `MacroBrief` is persisted to a new `macro_briefs` table, 1:1 with `ResearchRun`. |
| 7 | Themes stay inline strings; no theme-entity materialization in Phase 4. |
| 8 | `run_orchestrator.py` refactors to a strategy-keyed `StageScheme` registry. |
| 9 | GICS bootstrap stub expands to the 11 top-level sectors; synthesis prompt enumerates them; verifier rejects sector names outside this set. |
| 10 | Synthesis model is `gpt-5-mini` (pinned via module constant `SYNTHESIS_MODEL`). |
| 11 | Single integrated branch — no parallel sub-phases. |

Open items from the handoff resolved here:

- `MacroBriefScope.universe = Literal["us_equities"]` — single literal for the MVP. Widening to `str` with an allowlist validator is a Phase 5 concern.
- FRED series list is a hardcoded module constant `FRED_SERIES` in `app/services/strategies/funnel_research/config.py`, not an env knob.
- All confidence/conviction floats are constrained to `[0.0, 1.0]` via Pydantic `Field(ge=0.0, le=1.0)`.
- No frontend smoke test (web app ships no test runner).
- Verifier emits one `RunEvent(level=info)` per regeneration attempt for observability, mirroring Phase 3d's per-LLM-call event pattern.
- Bootstrap-under-concurrent-runs uses Phase 3c's existing upsert race-handling (`IntegrityError` catch + lookup); no advisory lock added in Phase 4.

## Schema Changes (Alembic `005_phase4_macro_brief`)

One migration, round-trip clean against SQLite per the Phase 2/3 convention.

```python
revision = "005"
down_revision = "004"
```

### `research_runs` alters

- `ticker` column → `nullable=True`. Existing rows keep their values; no backfill required.
- New `scope_payload` column → `JSON nullable`. Phase 1/2/3 rows are untouched (NULL).

```python
op.alter_column("research_runs", "ticker", nullable=True)
op.add_column(
    "research_runs",
    sa.Column("scope_payload", sa.JSON(), nullable=True),
)
```

### `macro_briefs` (new table)

```python
op.create_table(
    "macro_briefs",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("run_id", sa.Uuid(), nullable=False),
    sa.Column("themes", sa.JSON(), nullable=False),
    sa.Column("sector_calls", sa.JSON(), nullable=False),
    sa.Column("watch_items", sa.JSON(), nullable=False),
    sa.Column("cited_claims", sa.JSON(), nullable=False),
    sa.Column("proposed_hypotheses", sa.JSON(), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("verifier_status", sa.String(length=32), nullable=False),
    sa.Column("regeneration_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("evidence_ids", sa.JSON(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    ),
    sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
    sa.CheckConstraint(
        "verifier_status IN ('verified', 'quote_unverified')",
        name="ck_macro_briefs_verifier_status",
    ),
)
op.create_index("ix_macro_briefs_run_id", "macro_briefs", ["run_id"])
```

JSON-typed columns store the typed sub-models verbatim via `model_dump(mode="json")`. The unique constraint on `run_id` enforces the 1:1 contract; the ORM uses `selectinload` from `ResearchRun` for the GET path.

### ORM model — `app/db/models_macro.py`

```python
class MacroBrief(Base):
    __tablename__ = "macro_briefs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
        Index("ix_macro_briefs_run_id", "run_id"),
        CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_macro_briefs_verifier_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    themes: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    sector_calls: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    watch_items: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    cited_claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    proposed_hypotheses: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verifier_status: Mapped[str] = mapped_column(String(32), nullable=False)
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
```

Also adds `scope_payload: Mapped[dict[str, object] | None]` to `ResearchRun` and flips its `ticker` mapping to `Mapped[str | None]`.

## Typed Schemas — `app/schemas/macro_brief.py`

All schemas are frozen Pydantic v2 models (`model_config = ConfigDict(frozen=True, extra="forbid")`).

```python
class MacroBriefScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["macro"]
    universe: Literal["us_equities"]


class Theme(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    evidence_ids: list[uuid.UUID]
    confidence: float = Field(ge=0.0, le=1.0)


class SectorCallDirection(StrEnum):
    overweight = "overweight"
    underweight = "underweight"
    neutral = "neutral"


class SectorCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=64)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]


class WatchItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    reason: str
    evidence_ids: list[uuid.UUID]


class CitedClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_text: str
    exact_quote: str = Field(min_length=1)
    chunk_id: uuid.UUID
    source: str = Field(min_length=1, max_length=64)


class ProposedHypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_text: str
    scope_entity_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]


class VerifierStatus(StrEnum):
    verified = "verified"
    quote_unverified = "quote_unverified"


class MacroBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    themes: list[Theme]
    sector_calls: list[SectorCall]
    watch_items: list[WatchItem]
    cited_claims: list[CitedClaim]
    proposed_hypotheses: list[ProposedHypothesis]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class MacroBriefPublic(BaseModel):
    """Wire shape for GET /research-runs/{id}/macro-brief — adds chunk traceback."""
    model_config = ConfigDict(frozen=True)
    brief: MacroBrief
    chunks: list[ChunkLookup]


class ChunkLookup(BaseModel):
    model_config = ConfigDict(frozen=True)
    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    source: str
    text: str
    attributes: dict[str, object]
```

`MacroBriefPublic` wraps the brief plus a lookup table from `chunk_id` → chunk metadata so the UI can render claim → quote → source traceback in one fetch. The lookup is the union of all `chunk_id`s referenced from `cited_claims`.

`MacroBriefScope` is the typed shape for the `scope_payload` column. The `CreateResearchRunsRequest` validator parses incoming dicts into this model before persistence.

## Stage Scheme Refactor — `run_orchestrator.py`

Replace the three module constants `_RUNNING_STAGE_INDEX`, `_TERMINAL_STAGE_INDEX`, `_TOTAL_STAGES` with a strategy-keyed registry. The wire shape of `emit_stage_event` (`stage_name`, `stage_index`, `total_stages`) stays identical so the existing SSE consumers in `apps/web` continue to work.

```python
StageScheme = tuple[str, ...]

STAGE_SCHEMES: Mapping[str, StageScheme] = {
    "tradingagents": ("running",),
    "funnel_research": ("ingest", "digest", "synthesize", "verify"),
}

_TERMINAL_STAGE_NAMES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


def resolve_stage_position(
    *, strategy: str, stage_name: str
) -> tuple[int, int]:
    """Return (stage_index, total_stages) for an emit_stage_event call.

    Convention (preserved from Phase 1):
      - total_stages = len(scheme) + 1 (the +1 is the terminal slot)
      - in-flight stages are 1-indexed by their position in the scheme
      - terminal stages always use index = total_stages
    """
```

For `tradingagents`: `len(scheme)+1 == 2`; `running` is at 1/2, terminal at 2/2 — byte-identical to the existing implementation.

For `funnel_research`: `len(scheme)+1 == 5`; stages emit at 1/5, 2/5, 3/5, 4/5; terminal at 5/5.

Orchestrator call sites use a small helper:

```python
def _emit_strategy_stage(
    session: AsyncSession,
    *,
    run_id: UUID,
    strategy: str,
    stage_name: str,
    message: str | None = None,
    level: RunEventLevel = RunEventLevel.info,
) -> None:
    index, total = resolve_stage_position(strategy=strategy, stage_name=stage_name)
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name=stage_name,
        stage_index=index,
        total_stages=total,
        message=message,
        level=level,
    )
```

`RunOrchestrator.fail`, `cancel`, `_mark_running_and_load_config`, `_mark_failed`, `_persist_success` all switch to `_emit_strategy_stage`, looking up the strategy off the loaded `ResearchRun` row. The funnel strategy's `core.py` uses the same helper directly when emitting sub-stage events from `_ingest`, `_digest`, `_llm_call`, and `_verifier`.

Unknown strategy in `STAGE_SCHEMES` raises `RunOrchestratorError` — defends against silent regression when a new strategy is added without registry entry.

## New Source Client — `tiingo_news.py`

Separate module from `tiingo.py` because the news endpoint is documented independently and shares only the auth token. Module-local `_RATE_LIMITER` is sized conservatively (`rate_per_second=1.0`, `burst=3`, matching the existing `tiingo.py` budget; Tiingo's published limit is per-hour-tier, so a global per-second clamp is the safer choice).

```python
class TiingoNewsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: int
    title: str
    description: str | None
    url: str
    publishedDate: datetime  # noqa: N815 — Tiingo API field
    source: str
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


async def fetch_tiingo_news(
    *,
    client: httpx.AsyncClient,
    tickers: list[str] | None = None,
    limit: int = 50,
) -> tuple[list[TiingoNewsItem], str]:
    """GET https://api.tiingo.com/tiingo/news. Returns parsed list + content_hash."""
```

`tickers=None` returns top headlines (the Phase 4 macro use case). Auth: `Authorization: Token <tiingo_api_key>`, same header pattern as `tiingo.py`. Raises `SourceClientConfigError` when the key is missing.

`__init__.py` re-exports `TiingoNewsItem` and `fetch_tiingo_news`.

## New Ingestion Adapters

Each adapter mirrors the Phase 3b shape: own its own `async with session.begin()` block, route through `insert_or_get_evidence` for content-hash idempotency, and emit chunks via a paired chunker in `_chunkers.py`. Return an `IngestedEvidence` from `app/schemas/extraction.py`.

| Module | Source string | Document ID strategy | Chunker output |
|---|---|---|---|
| `ingestion/polymarket_events.py` | `"polymarket_events"` | `event.id` | One chunk per event: `{title, slug, category, active, closed}`. |
| `ingestion/kalshi_markets.py` | `"kalshi_markets"` | `market.ticker` | One chunk per market: `{title, yes_subtitle, status, close_time, last_price}`. |
| `ingestion/congress_bills.py` | `"congress_bills"` | `bill.number`+`bill.congress`+`bill.type` | One chunk per bill: `{number, title, latest_action_date, latest_action_text, sponsor}`. |
| `ingestion/tiingo_news_items.py` | `"tiingo_news"` | `news_item.id` (as str) | One chunk per article: `{title, source, publishedDate, tickers, description}`. |

Chunkers go into `_chunkers.py` next to the existing `chunk_fred_observations`, `chunk_sec_tickers`, `chunk_sec_submissions`. Each chunker computes `content_hash = sha256(chunk_text)` exactly like the existing chunkers.

Idempotency: re-ingesting the same payload twice returns the existing evidence + chunk count via `EvidenceUpdateConflictError`-free path (content_hash collision returns `was_inserted=False`). The Phase 3b regression test pattern (insert → re-insert → expect 0 new rows) is reused.

`app/services/ingestion/__init__.py` re-exports the four new `ingest_*` functions in alphabetical order alongside the existing three.

## GICS Expansion — `services/api/data/gics_industries.json`

Replace the 7-row industry-level stub with the 11 top-level GICS sectors. Each entry carries the documented 2-digit sector code and the canonical sector name:

```json
[
  {"gics_code": "10", "name": "Energy"},
  {"gics_code": "15", "name": "Materials"},
  {"gics_code": "20", "name": "Industrials"},
  {"gics_code": "25", "name": "Consumer Discretionary"},
  {"gics_code": "30", "name": "Consumer Staples"},
  {"gics_code": "35", "name": "Health Care"},
  {"gics_code": "40", "name": "Financials"},
  {"gics_code": "45", "name": "Information Technology"},
  {"gics_code": "50", "name": "Communication Services"},
  {"gics_code": "55", "name": "Utilities"},
  {"gics_code": "60", "name": "Real Estate"}
]
```

`app/services/entity_bootstrap/gics_sectors.py:bootstrap_from_gics` is unchanged — it already iterates the JSON, normalizes aliases, and upserts by `gics_code`. The expansion is a JSON-only change; the existing test `test_entity_bootstrap_gics.py` updates its row-count assertions.

Strategy's `_bootstrap.py` is a thin idempotent wrapper that calls `bootstrap_from_gics(session=session)` and returns the resulting `list[BootstrappedEntity]`. The 11 returned entity IDs are the candidate `sector_entity_id` values the synthesis prompt may use.

## Strategy Implementation — `app/services/strategies/funnel_research/`

### `config.py`

```python
from typing import Final

SYNTHESIS_MODEL: Final[str] = "gpt-5-mini"
MAX_REGENERATIONS: Final[int] = 2
PROMPT_VERSION: Final[str] = "macro-brief-v1"
MAX_RESPONSE_TOKENS: Final[int] = 8000

FRED_SERIES: Final[tuple[str, ...]] = (
    "CPIAUCSL",   # CPI, all urban consumers
    "UNRATE",     # Civilian unemployment rate
    "FEDFUNDS",   # Federal funds effective rate
    "GS10",       # 10-year treasury constant maturity
    "GS2",        # 2-year treasury constant maturity
)

ALLOWED_SECTOR_NAMES: Final[frozenset[str]] = frozenset({
    "Energy", "Materials", "Industrials", "Consumer Discretionary",
    "Consumer Staples", "Health Care", "Financials", "Information Technology",
    "Communication Services", "Utilities", "Real Estate",
})

TIINGO_NEWS_FETCH_LIMIT: Final[int] = 50
POLYMARKET_FETCH_LIMIT: Final[int] = 100
KALSHI_FETCH_LIMIT: Final[int] = 100
CONGRESS_BILLS_FETCH_LIMIT: Final[int] = 50
```

These are module-level constants (mirroring Phase 3d/3e's `config.py` style). Promotion to env knobs is a Phase 5 concern.

### `core.py` — `run_macro_brief(*, session, run_id)`

The single public coroutine. Wired from `app/workers/tasks.py` as the dispatch target when `run.strategy == "funnel_research"`. Signature mirrors how `RunOrchestrator.execute` is called today.

```python
class FunnelResearchError(Exception):
    """Raised when the funnel strategy cannot return a usable result."""


async def run_macro_brief(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
) -> None:
    """Execute Stage 1 of the research funnel for one run.

    Stage progression: ingest -> digest -> synthesize -> verify, then succeed.
    Budget pause/kill is routed through the injected orchestrator. Failures
    in source clients are isolated (warn-level RunEvent), they do not abort
    the run unless every source fails.
    """
```

Dependencies are injected (not constructed) so tests can substitute mocked clients without monkey-patching. The same pattern Phase 3d already uses for `_llm_call.call_llm_for_extraction`.

Flow:

1. Load `ResearchRun` + `scope_payload`. Validate scope via `MacroBriefScope.model_validate(...)`. On failure, `orchestrator.fail(run_id, "invalid scope")`.
2. Mark `running`, emit stage `ingest` (1/5).
3. `_bootstrap.run(session=session)` — idempotent GICS sector upsert.
4. `_ingest.run(session=session, http_client=http_client)` — parallel source fetch + ingest. Returns `IngestStageResult{evidence: list[IngestedEvidence], chunks: list[EvidenceChunkRef], source_payloads: SourcePayloads}`.
5. Emit stage `digest` (2/5). `_digest.run(payloads=...)` → typed `Digest` model.
6. Emit stage `synthesize` (3/5). `_llm_call.run(...)` → raw model output + cost log id.
7. Emit stage `verify` (4/5). `_verifier.run(...)` — loops at most `MAX_REGENERATIONS` times calling back into `_llm_call.run` with the failing-claims feedback message until either verified or cap hit.
8. `_hypotheses.run(...)` writes `Hypothesis` rows for each `ProposedHypothesis`.
9. `_persist.run(...)` writes the `macro_briefs` row and emits the final stage `succeeded` event via `RunOrchestrator._persist_success`-equivalent path (using `MacroBrief`-specific success wiring).
10. `BudgetPausedError` / `BudgetKilledError` from `_llm_call` propagate up and are caught in `core.run_macro_brief`, calling `orchestrator.pause` / `orchestrator.fail` respectively — same exception-handling shape as `extraction/_llm_call.py`.

Session ownership: every stage owns its own `async with session_factory()` block, mirroring how `RunOrchestrator` already structures stage transactions. The `LlmClient.complete` commit-the-session behavior is contained to `_llm_call.py`.

### `_ingest.py`

```python
@dataclass(frozen=True)
class SourcePayloads:
    fred: list[FredSeriesObservations]
    polymarket_events: list[PolymarketEvent]
    kalshi_markets: list[KalshiMarket]
    congress_bills: list[CongressBill]
    tiingo_news: list[TiingoNewsItem]


@dataclass(frozen=True)
class IngestStageResult:
    evidence: list[IngestedEvidence]
    chunks: list[EvidenceChunkRef]
    payloads: SourcePayloads
```

Source fetches run via `asyncio.gather(..., return_exceptions=True)`. Each exception → `emit_run_event(level=warn, message=f"{source} fetch failed: {exc}")` and the source is treated as empty for downstream stages. If *every* source fails, raise `FunnelResearchError("no sources returned data")` (caught in `core.py` → `orchestrator.fail`).

For each successful payload, call the matching `ingest_*` to persist evidence + chunks, then materialize `EvidenceChunkRef` rows from the new `evidence_chunks` for downstream use in the prompt and verifier.

### `_digest.py`

Pure deterministic Python. Produces:

```python
class Digest(BaseModel):
    model_config = ConfigDict(frozen=True)
    fred: list[FredDigestRow]            # series_id, latest_value, mom_delta, yoy_delta
    polymarket: list[PolymarketDigestRow] # title, current_odds, resolution_date
    kalshi: list[KalshiDigestRow]         # title, current_odds, close_time
    congress: list[CongressDigestRow]     # bill_number, title, action_date
    tiingo_news: list[NewsDigestRow]      # title, source, published_date, tickers
```

`render_markdown(digest: Digest) -> str` produces the section embedded in the synthesis prompt. Deterministic ordering (by series_id, by volume, by date) so prompt snapshots stay stable in tests.

### `_prompts.py`

```python
def build_synthesis_messages(
    *,
    scope: MacroBriefScope,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    allowed_sectors: frozenset[str],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regeneration_feedback: list[str] | None = None,
) -> list[LlmMessage]: ...
```

Message structure (top to bottom in the user message):

1. **Critical instruction block (1/2):** "Every `cited_claim.exact_quote` MUST appear verbatim in the chunks listed below. Every `sector_call.sector_name` MUST be one of the allowed sectors."
2. **Digest markdown table** (from `_digest.render_markdown`).
3. **Raw chunk corpus** — each chunk prefixed with `[chunk_id={uuid}, source={source}] <text>`.
4. **Allowed sectors** — enumerated 11 GICS sector names + their `sector_entity_id` UUIDs (synthesis output uses these UUIDs verbatim).
5. **Output schema** — JSON Schema description of `MacroBrief` (themes, sector_calls, watch_items, cited_claims, proposed_hypotheses, confidence, evidence_ids).
6. **Critical instruction block (2/2):** identical to (1) — positional redundancy per spec §9 "lost-in-the-middle mitigation."
7. If `regeneration_feedback` is non-empty: append a "Previous attempt rejected because: ..." section listing the failing claims/sectors. The regeneration loop in `_verifier` calls back into `_llm_call` with this populated.

The system message is constant: `"You are a macro-research synthesis engine. Produce a typed MacroBrief JSON object that obeys the schema and citation rules."`

`prompt_version = "macro-brief-v1"` (used by `LlmClient` call logging via the `prompt_hash` derived from the materialized message list).

### `_llm_call.py`

Follows the `extraction/_llm_call.py` pattern verbatim: takes injected `llm_complete`, `orchestrator_pause`, `orchestrator_fail` callables. Catches `BudgetPausedError` → `orchestrator_pause` + raise `FunnelResearchError`. Catches `BudgetKilledError` → `orchestrator_fail` + raise.

Parses the assistant content as JSON, validates against `MacroBrief` (raises `FunnelResearchError` on validation failure — the caller decides whether to regenerate or surface the failure as `verifier_status="quote_unverified"`; v0 spec routes JSON-validation failure to regeneration just like substring failure).

Uses `response_format={"type": "json_object"}` per `extraction/_llm_call.py`'s precedent (Phase 3d's `OpenAI Chat Completions` json-mode integration). `LlmClient.complete` already supports this; no changes to the client.

### `_verifier.py`

Deterministic verification with two checks per attempt:

1. **Cited-claim quote verification.** For each `claim in brief.cited_claims`:
   - Confirm `claim.chunk_id` belongs to the run's evidence corpus (lookup against the chunks returned by `_ingest`).
   - Whitespace-normalize both `claim.exact_quote` and the corresponding chunk text (`re.sub(r"\s+", " ", x).strip()`).
   - Confirm the normalized quote is a literal substring of the normalized chunk text.
2. **Sector-name validation.** For each `sector_call in brief.sector_calls`:
   - `sector_call.sector_name` ∈ `ALLOWED_SECTOR_NAMES`.
   - `sector_call.sector_entity_id` ∈ the GICS sector entity IDs returned by `_bootstrap`.

Failures produce structured reason strings: `"chunk_id not in corpus: ..."`, `"quote not in chunk: ..."`, `"sector name not in allowlist: ..."`, `"sector_entity_id mismatch: ..."`.

Regeneration loop:

```python
async def run(
    *,
    initial_brief: MacroBrief,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regenerate: Callable[[list[str]], Awaitable[MacroBrief]],
    emit_event: Callable[[str], None],
) -> VerifierResult:
    """Returns (final_brief, status, regeneration_count, rejection_reasons)."""
```

Behavior:

- Verify the initial brief. If clean → return `(brief, "verified", 0, [])`.
- Otherwise loop: emit `RunEvent(level=info, message=f"verifier regeneration {n}/{MAX_REGENERATIONS}: {N} rejections")`, call `regenerate(reasons)` to get a fresh `MacroBrief`, verify.
- Stop when verified or `n == MAX_REGENERATIONS`. On cap-hit, return the *last* candidate with status `"quote_unverified"` and `regeneration_count = MAX_REGENERATIONS`.

Emits one `RunEvent` per regeneration attempt for observability.

### `_hypotheses.py`

```python
async def run(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    proposed: list[ProposedHypothesis],
    sector_entity_ids: Mapping[str, uuid.UUID],
) -> list[uuid.UUID]: ...
```

For each `ProposedHypothesis`:

- `claim_text` = `proposed.claim_text`
- `scope_entity_ids` = `[str(eid) for eid in proposed.scope_entity_ids]` — stored as `list[str]` in the existing `hypotheses.scope_entity_ids` JSON column. Spec writer note: the column is `JSON list[str]` per `models_graph.Hypothesis`.
- `scope_theme_ids` = `[]` (themes are not entities in Phase 4).
- `status` = `"proposed"`.
- `proposed_by_run_id` = `run_id`.
- `belief` = `None`.
- `belief_history` = `[]`.

Returns the list of created `hypothesis_id`s for caller logging.

### `_persist.py`

Writes the `macro_briefs` row inside its own `async with session.begin()` block. Uses `model_dump(mode="json")` on each typed sub-list to populate the JSON columns. Computes `evidence_ids` as the deduplicated union of all `evidence_id`s referenced anywhere in the brief.

Emits the final success path: `RunOrchestrator._persist_success` is reused — but the funnel path has no `RunResult` shape because there is no TradingAgents adapter. Instead, `_persist.py` writes the macro brief, marks the run as `succeeded` directly (`run.status = RunStatus.succeeded`, `run.finished_at = utcnow`, `run.wall_clock_ms = ...`), emits the terminal stage event (`succeeded` at 5/5), and commits.

Final-rating columns (`final_rating`, `final_decision_summary`) stay NULL for funnel runs — `MacroBriefPublic` is the substantive output.

## API Surfaces

### `POST /research-runs` — gain a `funnel_research` branch

Update `CreateResearchRunsRequest` in `app/schemas/runs.py` to support two strategy branches. The simplest shape that does not break the existing TradingAgents request:

```python
class CreateResearchRunsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategyEnum = StrategyEnum.tradingagents
    trade_date: date
    tickers: list[str] | None = None
    scope_payload: MacroBriefScope | None = None
    analysts: list[AnalystKindEnum] = Field(default_factory=lambda: list(_DEFAULT_ANALYSTS))
    llm_provider: LlmProviderEnum | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    debate_depth: int = Field(default=3, ge=1, le=8)

    @model_validator(mode="after")
    def _check_strategy_inputs(self) -> Self:
        if self.strategy == StrategyEnum.tradingagents:
            if not self.tickers:
                raise ValueError("tradingagents strategy requires tickers")
            if self.scope_payload is not None:
                raise ValueError("scope_payload is only valid for funnel_research")
            if self.llm_provider is None or self.llm_model is None:
                raise ValueError("tradingagents strategy requires llm_provider and llm_model")
        elif self.strategy == StrategyEnum.funnel_research:
            if self.tickers:
                raise ValueError("funnel_research strategy does not accept tickers")
            if self.scope_payload is None:
                raise ValueError("funnel_research strategy requires scope_payload")
        return self
```

The `tickers` validator runs only when `tickers` is provided.

The route handler now branches on `payload.strategy`:

- `tradingagents` → existing per-ticker loop unchanged.
- `funnel_research` → create exactly one `ResearchRun(ticker=None, scope_payload=payload.scope_payload.model_dump(mode="json"), config={"prompt_version": PROMPT_VERSION})`, enqueue once.

Response shape stays `list[ResearchRunSummary]` (1-element list for funnel runs).

`ResearchRunSummary` is extended to allow `ticker: str | None`. `ResearchRunDetail` and `ResearchRunPublic` likewise.

### `GET /research-runs/{id}/macro-brief` — new route, new file

`app/api/routes/macro_briefs.py`:

```python
@router.get("/{run_id}/macro-brief", response_model=MacroBriefPublic)
async def get_macro_brief(
    run_id: uuid.UUID,
    session: SessionDep,
) -> MacroBriefPublic: ...
```

Behavior:

- Loads `ResearchRun` by id; if `strategy != funnel_research` → 404 "macro brief not available for this strategy".
- Loads the `macro_briefs` row by `run_id`; if missing → 404 "macro brief not yet available".
- Loads the chunks referenced by `cited_claims` (via `evidence_chunks.id IN (...)`) plus the parent `evidence.source` for each, projects them into the `ChunkLookup` shape.
- Returns `MacroBriefPublic(brief=..., chunks=[...])`.

Registered in `app/main.py` under the existing `/api/research-runs` router prefix.

### Workers — `app/workers/tasks.py`

Replace the current `orchestrator.fail(...)` stub with a dispatch table:

```python
async def _dispatch(run_id: UUID) -> None:
    strategy = await _load_strategy(run_id)
    adapter = TradingAgentsAdapter()
    orchestrator = RunOrchestrator(session_factory=session_factory, adapter=adapter)
    if strategy == Strategy.tradingagents.value:
        await orchestrator.execute(run_id)
        return
    if strategy == Strategy.funnel_research.value:
        async with httpx.AsyncClient() as http_client:
            llm_client = LlmClient(openai_client=_build_openai_client())
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=llm_client,
                orchestrator=orchestrator,
                http_client=http_client,
            )
        return
    await orchestrator.fail(
        run_id,
        f"strategy {strategy!r} is not implemented yet",
    )
```

`_build_openai_client()` uses the existing `openai_api_key` setting from `app/config.py`. The factory is colocated in `tasks.py` to keep the worker entrypoint self-contained.

## UI Surfaces (`apps/web`)

### "Run Macro Brief" button — `app/(app)/research/runs/page.tsx`

Add a second top-level action alongside the existing "New Run" dialog button. The new button opens a small confirmation that posts:

```json
{
  "strategy": "funnel_research",
  "scope_payload": { "kind": "macro", "universe": "us_equities" },
  "trade_date": "<today, US/Eastern>"
}
```

Navigates to the new run detail on success. The dialog component lives in `apps/web/app/(app)/research/runs/new-macro-brief-dialog.tsx` (mirroring the existing `new-run-dialog.tsx`).

### Run detail — `app/(app)/research/runs/[id]/run-detail.tsx`

Conditionally render based on `run.strategy`:

- `tradingagents` → existing component output (unchanged).
- `funnel_research` → new `<MacroBriefDetail run={run} />` component:
  - Stage timeline already reads `stage_index` / `total_stages` from the SSE `log` events. With the new `STAGE_SCHEMES` registry returning `total=5`, the existing timeline renders 5 dots automatically.
  - Cost meter — unchanged.
  - **Verifier status badge** — green `verified` / amber `quote_unverified` with the regeneration count.
  - **Themes** — list of `Theme` with confidence chips.
  - **Sector Calls** — table (sector_name | direction | conviction | evidence count).
  - **Watch Items** — list with name + reason.
  - **Cited Claims** — expandable rows; each row reveals `exact_quote` + linked `ChunkLookup.source`/`text` excerpt.
  - **Proposed Hypotheses** — list with claim_text + scoped sectors.

Data fetch: a new server action `getMacroBrief(runId)` in `apps/web/app/(app)/research/runs/[id]/actions.ts` calls `GET /research-runs/{id}/macro-brief` once per page load. Polled refresh on terminal status only — the existing SSE timeline drives in-flight updates.

OpenAPI schema regeneration (`pnpm generate:api`) is required after the backend ships. The generated `lib/api/schema.ts` exposes the new response type.

## Tests

### Backend

| Test file | Coverage |
|---|---|
| `test_alembic_phase4_round_trip.py` | `alembic upgrade head` + `alembic check` + `alembic downgrade base` on SQLite; asserts no drift, asserts `research_runs.ticker` is nullable post-upgrade, asserts `macro_briefs` exists and is dropped on downgrade. |
| `test_db_models_macro.py` | ORM CRUD: insert a `MacroBrief`, round-trip JSON columns, assert `verifier_status` check constraint rejects an invalid value, assert `run_id` uniqueness. |
| `test_schemas_macro_brief.py` | `MacroBriefScope` literals, range validators on confidence/conviction, `MacroBrief` `extra="forbid"` rejection of unknown fields. |
| `test_run_orchestrator_stage_scheme.py` | `resolve_stage_position("tradingagents", "running") == (1, 2)`. `resolve_stage_position("funnel_research", "digest") == (2, 5)`. Terminal stage names resolve to `(total, total)`. Unknown strategy raises `RunOrchestratorError`. Existing tradingagents tests in `test_models.py` continue to pass. |
| `test_source_clients_tiingo_news.py` | Respx-mocked happy path → list of `TiingoNewsItem`. Missing key → `SourceClientConfigError`. 429 retry path. Content hash matches. |
| `test_ingestion_polymarket_events.py` | Mocked client payload → `IngestedEvidence` with content hash + chunk count. Re-ingest returns the existing evidence row (idempotency). |
| `test_ingestion_kalshi_markets.py` | Same shape as polymarket. |
| `test_ingestion_congress_bills.py` | Same shape; verifies `document_id` keying on `(congress, type, number)`. |
| `test_ingestion_tiingo_news_items.py` | Same shape; deterministic chunk ordering. |
| `test_funnel_research_digest.py` | Snapshot test: fixed `SourcePayloads` → fixed `Digest`. `render_markdown` output is byte-stable. |
| `test_funnel_research_prompts.py` | Built messages contain (a) opening critical-instruction block, (b) all chunk_ids, (c) all 11 allowed sectors, (d) closing critical-instruction block. Regeneration feedback appended when provided. `prompt_hash` is stable for the same inputs. |
| `test_funnel_research_verifier.py` | Substring positive case, substring negative case, whitespace-normalization positive case, fabricated chunk_id negative case, invalid sector name negative case, mismatched sector_entity_id negative case. Regeneration loop: 0 regen happy path, 1 regen recovers, 2 regen cap with `quote_unverified` persisted. RunEvent emitted per regeneration. |
| `test_funnel_research_llm_call.py` | `BudgetPausedError` → `orchestrator_pause` called + `FunnelResearchError` raised. Same for kill. Successful happy-path return. Invalid JSON output → `FunnelResearchError`. |
| `test_funnel_research_hypotheses.py` | `ProposedHypothesis` writes a `Hypothesis` row with the right `scope_entity_ids` (as `list[str]`), `proposed_by_run_id`, `status="proposed"`, `belief=None`. Empty input writes zero rows. |
| `test_funnel_research_persist.py` | `macro_briefs` row written with all JSON columns populated. `evidence_ids` is the dedup union. Run row flipped to `succeeded`, stage event 5/5 emitted. |
| `test_funnel_research_core.py` | End-to-end Stage 1 with respx-mocked source clients + fake `LlmClient` returning a hand-crafted JSON. Produces a verified `MacroBrief` row + N `Hypothesis` rows + 5 stage events. Partial source failure (one source raises) emits a warn-level `RunEvent` and still succeeds. Total source failure → `orchestrator.fail`. Budget-pause path leaves run in `paused`. |
| `test_research_runs_funnel_post.py` | `POST /research-runs` with `strategy=funnel_research` + valid scope → 1 run created with `ticker=None`. Missing `scope_payload` → 422. Includes `tickers` → 422. Wrong scope kind → 422. |
| `test_research_runs_macro_brief_get.py` | 404 for non-funnel runs, 404 for funnel runs without a brief yet, 200 with full `MacroBriefPublic` including chunk traceback when the brief exists. |
| `test_entity_bootstrap_gics.py` (modified) | Updated row count: 11 sectors instead of 7. Asserts each canonical name is present. |

Target test count: roughly **60–80 new tests**, bringing the suite from a baseline of ~534 to ~600+.

### Frontend

No automated tests. Manual verification per the gates below.

## Verification Gates

From `services/api`:

```bash
.venv/bin/python -m pytest                         # all tests pass
.venv/bin/python -m ruff check                     # clean
.venv/bin/python -m mypy app                       # strict clean

rm -f /tmp/alembic_check.db
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic check
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic downgrade base
rm -f /tmp/alembic_check.db
```

From `apps/web`:

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm generate:api    # after backend is running
```

Manual smoke (UI):

1. Start API + worker + web app locally.
2. Click **Run Macro Brief** on `/research/runs`.
3. Observe 4-stage timeline progress to `verify` then `succeeded` (5/5).
4. Open the run detail; verify the verifier badge, themes, sector calls, watch items, cited claims, proposed hypotheses render.
5. Expand a cited claim; verify the source chunk text contains the highlighted quote verbatim.
6. Query the `hypotheses` table directly; verify N rows exist with `proposed_by_run_id == <run.id>`.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Synthesis model hallucinates a sector name not in the allowlist, exhausting both regenerations. | Verifier persists with `quote_unverified` rather than failing the run. UI badge surfaces the state. Operator can re-run; if pattern recurs, tighten prompt or bump to `gpt-5`. |
| One source client outage takes down the whole stage. | `_ingest` uses `asyncio.gather(return_exceptions=True)` + per-source warn-level events. Stage proceeds with whatever payloads succeeded. Total-failure case routes to `orchestrator.fail`. |
| `LlmClient.complete` commits the caller-provided session — interleaved writes could collide. | Each strategy stage owns its own `async with session_factory()` block. `_llm_call.py` is the only call site for the LLM. |
| Stage scheme refactor breaks existing TradingAgents tests. | `StageScheme["tradingagents"] = ("running",)` produces identical `(stage_index, total_stages)` pairs (1/2 running, 2/2 terminal) — round-trip equivalent. Existing `test_models.py` and `test_adapter_mock.py` continue to pass; the new `test_run_orchestrator_stage_scheme.py` pins this. |
| Bootstrap race when two funnel runs start simultaneously. | Phase 3c's `IntegrityError`-catch path in `entity_bootstrap/_persist.py` already handles concurrent inserts on the `(type, primary_external_id_key)` unique key. No advisory lock required at this concurrency level. |
| Migration leaves `research_runs.ticker` nullable but old rows + new not-null assumption in downstream queries (`ResearchRun.ticker` typed as `str`). | `ResearchRun.ticker` ORM mapping flips to `Mapped[str | None]`; `ResearchRunSummary`/`ResearchRunDetail` schemas widen `ticker: str | None`. Backwards-compat: TradingAgents callers always supply a non-null ticker. |
| `model_dump(mode="json")` for typed sub-lists produces dicts with UUIDs as strings; downstream consumers expect `uuid.UUID`. | `MacroBrief` validators accept both `uuid.UUID` and string-form UUIDs via Pydantic's default coercion. The `MacroBriefPublic` GET response normalizes back to UUID strings via FastAPI's response serializer. |
| Prompt grows unboundedly with chunk count. | `_ingest` caps each source's fetch limit (constants in `config.py`). Worst-case payload (5 FRED series × ~12 obs each + 100 polymarket + 100 kalshi + 50 bills + 50 news) is ~300–400 chunks. `gpt-5-mini` has a 1M context window; comfortably under. Worst-case prompt cost ≈ $0.014 per the brainstorming math. |
| Verifier whitespace normalization too lenient — accepts a quote that drops a sentence. | Substring match still requires every character in the (normalized) quote to appear in (normalized) chunk text in order; sentence drops change the chunk → fail. Tests cover this edge. |

## Cross-Cuts With Existing Substrate

- **`Hypothesis` ORM model** — `scope_entity_ids: Mapped[list[str]]` stores UUIDs as strings in the JSON column. `_hypotheses.py` serializes with `str(uuid)`.
- **`Evidence` + `EvidenceChunk`** — re-used unchanged from Phase 2/3. New ingestion adapters write through the existing `insert_or_get_evidence` + `insert_chunks` helpers.
- **`bootstrap_from_gics`** — already exists in `entity_bootstrap/gics_sectors.py` (named `bootstrap_from_gics`, not `bootstrap_from_gics_sectors` as the handoff casually wrote). `_bootstrap.py` is a thin wrapper that calls it.
- **`LlmClient.complete`** — unchanged. Phase 4's `_llm_call.py` is the second caller (after extraction); the budget-error handling pattern is reused verbatim.
- **`model_pricing.py`** — `gpt-5-mini` is already priced. No change.
- **`config.py`** — `tiingo_api_key` already exists. No new settings.
- **SSE stage events** — wire shape is preserved (`stage_index`, `total_stages` as integers); only the resolution logic moves into the `STAGE_SCHEMES` registry.

## Out-Of-Scope Items Carried Forward To Phase 5

- Stage 2 sector fan-out (parallel per-sector deep dives with budget guards).
- Per-chunk extraction (`extract_from_chunk`) invoked as part of the synthesis path.
- Theme promotion to first-class `entities` rows + entity-resolution wiring on the synthesis path.
- LLM-contradiction-judge verifier (cheap-model second pass to catch quoted-but-misrepresented claims).
- Budget race-condition hardening under fan-out.
- Process-local rate-limiter promotion to shared (Redis-backed) limiter for multi-worker deploys.
- Full 150-industry GICS bootstrap.
- Frontend test runner (vitest + react-testing-library) and Playwright smoke for the macro-brief flow.
- Hypothesis-listing UI surface.
- Prompt iteration framework + A/B comparison harness.

## File Map

```
services/api/
├── alembic/versions/005_phase4_macro_brief.py       # NEW
├── app/
│   ├── api/routes/macro_briefs.py                   # NEW
│   ├── api/routes/research_runs.py                  # MODIFIED — funnel_research POST branch
│   ├── db/models_macro.py                           # NEW
│   ├── db/models_runs.py                            # MODIFIED — ticker nullable, scope_payload
│   ├── main.py                                      # MODIFIED — register macro_briefs router
│   ├── schemas/macro_brief.py                       # NEW
│   ├── schemas/runs.py                              # MODIFIED — multi-strategy request shape
│   ├── services/ingestion/_chunkers.py              # MODIFIED — 4 new chunkers
│   ├── services/ingestion/__init__.py               # MODIFIED — export new ingest_*
│   ├── services/ingestion/congress_bills.py         # NEW
│   ├── services/ingestion/kalshi_markets.py         # NEW
│   ├── services/ingestion/polymarket_events.py      # NEW
│   ├── services/ingestion/tiingo_news_items.py      # NEW
│   ├── services/run_orchestrator.py                 # MODIFIED — StageScheme registry
│   ├── services/source_clients/__init__.py          # MODIFIED — export tiingo_news
│   ├── services/source_clients/tiingo_news.py       # NEW
│   ├── services/strategies/__init__.py              # NEW
│   ├── services/strategies/funnel_research/         # NEW (10 modules)
│   ├── workers/tasks.py                             # MODIFIED — strategy dispatch
│   └── data/gics_industries.json                    # REPLACED — 11 sectors
└── tests/                                           # ~19 NEW test files + 1 modified

apps/web/
├── app/(app)/research/runs/page.tsx                 # MODIFIED — add macro brief button
├── app/(app)/research/runs/new-macro-brief-dialog.tsx # NEW
├── app/(app)/research/runs/[id]/run-detail.tsx      # MODIFIED — strategy-aware rendering
├── app/(app)/research/runs/[id]/macro-brief-detail.tsx # NEW
├── app/(app)/research/runs/[id]/actions.ts          # MODIFIED — getMacroBrief
└── lib/api/schema.ts                                # REGENERATED via generate:api
```

Estimated diff size: ~2200–3000 insertions, ~150 deletions, mostly in three places — the funnel strategy package, the 4 ingestion adapters + chunkers, and the macro-brief UI components.

## Implementation Sequencing (Single Branch)

1. Migration + ORM model (`models_macro.py`, `005_phase4_macro_brief.py`). Round-trip clean.
2. Typed schemas (`schemas/macro_brief.py`) + extension of `schemas/runs.py`.
3. `StageScheme` registry refactor in `run_orchestrator.py`. Existing tests pass.
4. GICS JSON expansion + `bootstrap_from_gics` test update.
5. `tiingo_news.py` source client + tests.
6. 4 ingestion adapters + 4 chunkers + tests.
7. `_digest.py` (pure-Python) + tests.
8. `_prompts.py` + `_llm_call.py` + tests (mocked LLM).
9. `_verifier.py` + regeneration loop + tests.
10. `_hypotheses.py` + tests.
11. `_persist.py` + tests.
12. `core.py:run_macro_brief` + end-to-end test with mocked LLM and respx.
13. `POST /research-runs` funnel branch + `GET /research-runs/{id}/macro-brief` route + tests.
14. `workers/tasks.py` dispatch update.
15. `apps/web` UI: macro brief button, dialog, detail view, schema regeneration.
16. Manual UI smoke per the gates above.
