# Phase 5 — Broad Funnel Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `funnel_research` from a single-stage macro brief into a parent-run Stage 2 sector fan-out, plus carry-overs from Phase 4: public `scope_payload`, Redis budget lock and rate limiter, LLM judge, theme promotion, hypothesis UI, frontend tests, full GICS hierarchy, prompt iteration harness.

**Spec:** `docs/superpowers/specs/2026-05-19-phase-5-broad-funnel-expansion-design.md`
**Working directory:** `services/api/` for pytest/ruff/mypy/alembic; `apps/web/` for typecheck/lint/build/test/e2e.
**Branch:** Continue on `freddysongg/trading-llm-signals`. Do not rename.

---

## Commit Order

Implementation lands in small commits in this order. Each commit ends green on its own slice (tests + lint + types). A review pass runs after each numbered task.

1. **Schemas + migration 006** (no behavior change; types-only).
2. **`scope_payload` exposure** on run response schemas + UI label.
3. **Redis budget lock + rate limiter** (no behavior change in dev/test; redis-only path is opt-in).
4. **Full GICS hierarchy** + bounded sector constituent config.
5. **Polygon aggregates ingestion** (only if sector fan-out uses it).
6. **Sector synthesis core**: selector → evidence → extraction → graph → prompts → llm_call → verifier → persist.
7. **LLM judge** wired into macro + sector verify.
8. **Stage 5/6 wiring**: `run_macro_brief` extended through `sector_fanout → consolidate → succeeded`.
9. **Theme promotion** at consolidate.
10. **Hypotheses API + UI**.
11. **Prompt iteration harness**.
12. **Vitest + RTL + Playwright** wiring.

---

## Task 1: Schemas + Migration 006

- [ ] **Step 1:** Add `services/api/alembic/versions/006_phase5_sector_briefs.py`.

  - `op.add_column("macro_briefs", sa.Column("judge_status", sa.Text(), nullable=False, server_default="not_run"))`
  - `op.create_check_constraint("ck_macro_briefs_judge_status", "macro_briefs", "judge_status IN ('not_run','passed','flagged')")`
  - `op.add_column("macro_briefs", sa.Column("judge_reasons", postgresql.JSONB, nullable=True))`
  - `op.add_column("macro_briefs", sa.Column("judge_call_id", postgresql.UUID(as_uuid=True), nullable=True))`
  - `op.create_foreign_key("fk_macro_briefs_judge_call_id_llm_call_logs", "macro_briefs", "llm_call_logs", ["judge_call_id"], ["id"], ondelete="SET NULL")`
  - `op.create_table("sector_briefs", ...)` per spec (id, run_id FK→research_runs cascade, sector_entity_id FK→entities restrict, direction CHECK, payload JSONB, verifier_status CHECK, regeneration_count int default 0, judge_status default 'not_run' + CHECK, judge_reasons jsonb, judge_call_id FK→llm_call_logs set null, wall_clock_ms int, created_at timestamptz default now(), UNIQUE(run_id, sector_entity_id))
  - `op.create_index("ix_sector_briefs_run_id", "sector_briefs", ["run_id"])`
  - Reverse: drop table, drop columns, drop constraints in reverse order. Use `with op.batch_alter_table` for SQLite round-trip compatibility.

- [ ] **Step 2:** Add `services/api/app/db/models_sector.py`:

  ```python
  class SectorBrief(Base):
      __tablename__ = "sector_briefs"
      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
      sector_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
      direction: Mapped[str] = mapped_column(Text, nullable=False)
      payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
      verifier_status: Mapped[str] = mapped_column(Text, nullable=False)
      regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
      judge_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_run")
      judge_reasons: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
      judge_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_call_logs.id", ondelete="SET NULL"), nullable=True)
      wall_clock_ms: Mapped[int] = mapped_column(Integer, nullable=False)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
      __table_args__ = (UniqueConstraint("run_id", "sector_entity_id"), CheckConstraint("direction IN ('overweight','underweight','neutral')"), CheckConstraint("verifier_status IN ('verified','quote_unverified')"), CheckConstraint("judge_status IN ('not_run','passed','flagged')"))
  ```

- [ ] **Step 3:** Modify `services/api/app/db/models_macro.py` to add `judge_status` (Text, default 'not_run'), `judge_reasons` (JSONB nullable), `judge_call_id` (FK nullable) columns + matching CheckConstraint.

- [ ] **Step 4:** Add `services/api/app/schemas/sector_brief.py` per spec types (`SectorCompanyIdea`, `SectorBrief`, `SectorBriefPublic`, `JudgePublic`, `JudgeStatus`).

- [ ] **Step 5:** Modify `services/api/app/schemas/macro_brief.py` to add `judge: JudgePublic` and `sector_briefs: list[SectorBriefPublic]` to `MacroBriefPublic`. Export `JudgePublic` and `JudgeStatus`.

- [ ] **Step 6:** Add tests:

  - `tests/test_alembic_phase5_round_trip.py` — upgrade → downgrade → upgrade on SQLite.
  - `tests/test_db_models_sector.py` — unique constraint, default values, check constraints.
  - `tests/test_schemas_sector_brief.py` — type happy paths + validation rejects.

- [ ] **Step 7:** Verify: `pytest -q tests/test_alembic_phase5_round_trip.py tests/test_db_models_sector.py tests/test_schemas_sector_brief.py`, `ruff check`, `mypy app`.

- [ ] **Step 8:** Commit: `add: phase 5 sector_briefs migration, sector brief schemas, judge fields on macro briefs`.

---

## Task 2: `scope_payload` Exposure + UI Label

- [ ] **Step 1:** Add `scope_payload: dict[str, object] | None = None` to `ResearchRunSummary`, `ResearchRunDetail`, `ResearchRunPublic` in `services/api/app/schemas/runs.py`. Ensure SQLAlchemy `JSON` column maps through `from_attributes=True` cleanly (it already does for the existing `config` field).

- [ ] **Step 2:** Update route handlers/serializers in `services/api/app/api/routes/research_runs.py` if any explicitly construct `ResearchRunSummary`/`Public` from selected columns (the existing path uses ORM passthrough; verify).

- [ ] **Step 3:** Add `tests/test_schemas_runs_scope_payload.py` covering null + populated cases. Add `tests/test_runs_scope_payload_api.py` checking `GET /api/research/runs` and `GET /api/research/runs/{id}` echo the stored payload for a `funnel_research` run.

- [ ] **Step 4:** Regenerate the web OpenAPI schema: from `services/api/`, run `.venv/bin/python -m app.main openapi --dump` (or the existing CLI used in `556dcb4`). Output to `apps/web/openapi.json` and regenerate `apps/web/lib/api/schema.ts`.

- [ ] **Step 5:** Modify `apps/web/app/(app)/research/runs/page.tsx`. For each row where `strategy === "funnel_research"`, render `MACRO · US EQUITIES` (uppercase + `·`) as the label that currently shows the ticker. Source from `scope_payload.kind` (`macro`) and `scope_payload.universe` (`us_equities`).

- [ ] **Step 6:** Verify backend: `pytest -q`. Verify web: `pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web build`.

- [ ] **Step 7:** Commit: `add: scope_payload on run response schemas, render macro·us_equities label for funnel runs`.

---

## Task 3: Redis Budget Lock + Token Bucket

- [ ] **Step 1:** Add `services/api/app/services/redis_lock.py`:

  ```python
  class BudgetLockProtocol(Protocol):
      async def __aenter__(self) -> "BudgetLockProtocol": ...
      async def __aexit__(self, *_: object) -> None: ...

  class LocalBudgetLock(BudgetLockProtocol):
      """asyncio.Lock-keyed by (run_id|None). Process-local."""

  class RedisBudgetLock(BudgetLockProtocol):
      """SETNX with TTL fallback. Exponential backoff capped at 250ms."""

  def make_budget_lock_factory(redis_url: str | None) -> Callable[[UUID | None], BudgetLockProtocol]: ...
  ```

  Use `redis.asyncio` (already a transitive dep) or `aioredis`. Verify which is available before pinning. If neither is in pyproject, add `redis>=5.0` (which ships `redis.asyncio`).

- [ ] **Step 2:** Modify `app/services/llm/client.py`:

  - `LlmClient.__init__` accepts `lock_factory: Callable[[UUID | None], BudgetLockProtocol] | None = None`.
  - In `_evaluate_and_persist`, wrap the prior-sum + decision + persist sequence in `async with self._lock_factory(run_id):` when factory is provided; fallback path is unchanged.
  - Pure-function callers (extraction tests etc.) get the default `LocalBudgetLock` factory.

- [ ] **Step 3:** Refactor `app/services/source_clients/_rate_limit.py`:

  - Extract `RateLimiterProtocol`.
  - Rename existing class to `LocalTokenBucket` (keep alias `RateLimiter = LocalTokenBucket` to avoid churn in source clients).
  - Add `RedisTokenBucket` with a Lua refill-+-deduct script. Same `acquire()` shape.
  - Add `make_rate_limiter(*, name, rate_per_second, burst, redis_url=None)` factory.

- [ ] **Step 4:** Wire `app/workers/tasks.py`:

  - On worker process start, read `settings.redis_url`.
  - Construct one budget lock factory and pass it to the `LlmClient` used by funnel runs.
  - Construct source-client rate limiters via `make_rate_limiter(...)`. Keep module singletons by referencing the factory at module import time (lazy if `settings.redis_url` is None).

- [ ] **Step 5:** Tests:

  - `tests/test_redis_budget_lock.py` — uses `fakeredis.aioredis` (add as dev dep) to test lock acquisition + contention + TTL expiry.
  - `tests/test_redis_rate_limiter.py` — `fakeredis` to verify refill behavior matches the local bucket within tolerance.
  - Update `tests/test_llm_client_budget.py` (if it exists) to inject a `LocalBudgetLock` factory and confirm it's used.

- [ ] **Step 6:** Verify: `pytest -q`, `ruff check`, `mypy app`.

- [ ] **Step 7:** Commit: `add: redis budget lock, redis token bucket rate limiter, wire worker-side factories`.

---

## Task 4: Full GICS Hierarchy + Sector Constituent Config

- [ ] **Step 1:** Replace `services/api/app/data/gics_industries.json` with hierarchical entries: `[{gics_code, name, level, parent_gics_code}]`. Source: GICS 2023 publication (cite in the JSON's leading `_comment` field).

- [ ] **Step 2:** Modify `app/services/entity_bootstrap/gics_sectors.py` (or equivalent existing entrypoint):

  - Load all rows.
  - For each row, upsert `entities` with `type='sector'`, `canonical_name=name`, `attributes={'gics_code': code, 'gics_level': level, 'parent_gics_code': parent or None}`. Reuse existing idempotency.
  - Update `_bootstrap.py` in `funnel_research/` to filter for `level == 1` when seeding Stage 1 vocabulary.

- [ ] **Step 3:** Replace any hardcoded list of 11 sector names with a query/helper `load_top_level_sector_names(session) -> list[str]` and use it in `_verifier.py`.

- [ ] **Step 4:** Add `services/api/app/data/sector_constituents.json` mapping each top-level sector name to `{proxy_ticker, representative_tickers: list[str] (≤5)}`.

- [ ] **Step 5:** Tests:

  - Update `tests/test_entity_bootstrap_gics.py` (already in repo) to assert full hierarchy bootstrap. Rename or split if it grew too large.
  - Add `tests/test_entity_bootstrap_gics_hierarchy.py` for level-filter helper.

- [ ] **Step 6:** Verify: `pytest -q`, `ruff check`, `mypy app`.

- [ ] **Step 7:** Commit: `update: gics seed to full hierarchy, add sector constituent config, derive top-level vocabulary from db`.

---

## Task 5: Polygon Aggregates Ingestion (Sector Evidence)

Only land this commit if Stage 2 sector synthesis consumes Polygon aggregates. If sector evidence uses only Tiingo+EDGAR+event markets, skip this task and renumber subsequent tasks.

- [ ] **Step 1:** Add `services/api/app/services/source_clients/polygon.py::fetch_aggregates(ticker, *, from_date, to_date, multiplier=1, timespan='day')` if the existing module lacks it. Use shared rate limiter.

- [ ] **Step 2:** Add `services/api/app/services/ingestion/polygon_aggregates.py::ingest_polygon_aggregates`:

  - Input: ticker, list of bar dicts.
  - Persists one `evidence` row with `source='polygon_aggregates'`, `source_document_id=f'{ticker}:{from_date}:{to_date}'`, content hash over the bars.
  - Splits into `evidence_chunks` via a new `_chunkers.polygon_aggregate_chunker` (one chunk per bar with text rendered as a single deterministic line).

- [ ] **Step 3:** Tests: respx mock + DB round trip + idempotency.

- [ ] **Step 4:** Verify and commit: `add: polygon aggregates ingestion, chunker, bounded daily windows`.

---

## Task 6: Sector Synthesis Core

This is the largest task. Split into sub-commits 6a–6h, each green on its own slice.

### 6a: Sector Selector

- [ ] Add `app/services/strategies/funnel_research/sector/__init__.py` and `sector/selector.py`. `select_sectors(brief: MacroBrief, max_count: int) -> list[SectorCall]` ordered by `(direction!=neutral desc, conviction desc, sector_name asc)`.
- [ ] Test: `tests/test_funnel_research_sector_selector.py` covering empty, all-neutral, mixed, ties.
- [ ] Commit: `add: funnel research sector selector with conviction ordering`.

### 6b: Sector Evidence Fetch + Ingest

- [ ] Add `sector/evidence.py::fetch_sector_evidence(session, *, sector_call, http_client, fetcher, constituent_map)`. Returns `IngestedEvidence` list using existing ingestion modules per source.
- [ ] Reuse `default_fetcher()` and per-source warn-level failure isolation.
- [ ] Tests with respx fixtures covering: all sources succeed, one source fails (skip), all sources fail (raise warn-and-empty).
- [ ] Commit: `add: sector evidence fetch and ingest with per-source warn isolation`.

### 6c: Extraction Orchestration

- [ ] Add `sector/extraction.py::extract_sector_chunks(session, *, run_id, chunks, llm_client)`. Wraps existing `extract_from_chunk` under per-run `asyncio.Semaphore(4)`. Returns list of accepted `CandidateEntity` + `CandidateRelation`.
- [ ] Tests verify semaphore bound, error isolation, downstream collection.
- [ ] Commit: `add: bounded extraction orchestration for sector chunks`.

### 6d: Graph Persistence

- [ ] Add `sector/graph.py::persist_candidates(session, *, run_id, candidates, relations)`. For each candidate, run entity resolution; persist only relations where both endpoints resolve.
- [ ] Tests cover both-resolved, one-unresolved (skip relation, keep entity), conflict (review queue path).
- [ ] Commit: `add: sector graph persistence with relation guard`.

### 6e: Sector Prompts

- [ ] Add `sector/prompts.py::build_sector_messages(*, macro_brief, sector_call, digest, chunks)`. Re-uses positional redundancy pattern from `_prompts.py`.
- [ ] Tests assert message shape, vocabulary inclusion, no PII leakage.
- [ ] Commit: `add: sector synthesis prompts with macro context`.

### 6f: Sector LLM Call

- [ ] Add `sector/llm_call.py::call_sector_synthesis(...)`. Mirrors `_llm_call.call_synthesis` with sector messages.
- [ ] Tests for budget pause/kill routing, evidence_ids propagation.
- [ ] Commit: `add: sector synthesis llm call wrapper`.

### 6g: Sector Verifier

- [ ] Add `sector/verifier.py::verify_sector_brief(...) -> RegenResult`. Deterministic substring + sector-name allowlist + sector-name match assertion.
- [ ] Tests cover verified, quote_unverified, sector-mismatch regen, regen cap reached.
- [ ] Commit: `add: sector deterministic verifier with regen loop`.

### 6h: Sector Persist

- [ ] Add `sector/persist.py::persist_sector_brief(session, *, run_id, brief, judge, wall_clock_ms)`.
- [ ] Tests for happy path, unique-constraint conflict, judge fields persistence.
- [ ] Commit: `add: sector_briefs row writer with judge fields`.

---

## Task 7: LLM Judge

- [ ] **Step 1:** Add `app/services/strategies/funnel_research/_judge.py::run_judge(*, session, run_id, llm_client, brief, brief_kind)`. Returns `JudgeOutcome(status: JudgeStatus, reasons: list[str], call_id: UUID | None)`.

- [ ] **Step 2:** Wire judge into macro verify path (`run_regen_loop` callers in `core.py`) and sector verify path. If deterministic verify returns `quote_unverified`, set `judge_status=not_run`. If `verified`, run the judge; if `flagged`, feed reasons into the regen feedback (counts against existing cap).

- [ ] **Step 3:** Update `persist_macro_brief` to persist `judge_status`, `judge_reasons`, `judge_call_id`. Same for `persist_sector_brief`.

- [ ] **Step 4:** Update `/research-runs/{id}/macro-brief` to include judge data on the brief and on each sector brief.

- [ ] **Step 5:** Tests:
  - `tests/test_funnel_research_judge.py` — judge passes, flags, error path (defaults to `not_run` with warn event).
  - Update `tests/test_funnel_research_persist.py` for judge column persistence.

- [ ] **Step 6:** Commit: `add: llm judge for macro and sector outputs, regen integration`.

---

## Task 8: Stage 5/6 Wiring

- [ ] **Step 1:** Extend `STAGE_SCHEMES["funnel_research"]` to `("ingest", "digest", "synthesize", "verify", "sector_fanout", "consolidate")` in `app/services/run_orchestrator.py`. Verify `resolve_stage_position` still works for `succeeded` (already-mapped terminal).

- [ ] **Step 2:** Extend `run_macro_brief` in `app/services/strategies/funnel_research/core.py`:

  - After macro persist, emit `sector_fanout` stage event.
  - Call `run_sector_fanout(session_factory, run_id, llm_client, http_client, fetcher, macro_brief)` under `asyncio.Semaphore(2)`.
  - On all-sectors-failed: orchestrator.fail with reason `"all sector fan-outs failed"`. Otherwise continue.
  - Emit `consolidate` stage event.
  - Call theme promotion (Task 9).
  - Emit `succeeded` terminal stage. Set run status to `succeeded`.

- [ ] **Step 3:** Update `tests/test_run_orchestrator_stage_scheme.py` for the new stage scheme. Add `tests/test_funnel_research_core_phase5.py` covering: happy path with 2 sectors, one sector fails, all sectors fail, no sector calls (skip fan-out, still consolidate + succeed).

- [ ] **Step 4:** Commit: `add: funnel research stage 2 fan-out wiring through consolidate stage`.

---

## Task 9: Theme Promotion

- [ ] **Step 1:** Add `app/services/strategies/funnel_research/_themes.py::promote_themes(*, session, run_id) -> list[uuid.UUID]`. Returns promoted entity ids.

- [ ] **Step 2:** Normalize themes via `_normalize_slug(name) -> str` (lower, NFKD ASCII fold, collapse whitespace).

- [ ] **Step 3:** Insert `entities` row with `type='theme'`, `canonical_name=display_label`, `attributes={'normalized_slug': slug}`. Use `ON CONFLICT DO NOTHING` over `(type, attributes->>'normalized_slug')` if a partial unique index exists; otherwise probe + insert with a transactional retry.

- [ ] **Step 4:** Backfill `hypotheses.scope_theme_ids` for hypotheses created by this run whose `claim_text` contains the display label (case-insensitive substring). Deduplicate.

- [ ] **Step 5:** Tests in `tests/test_funnel_research_themes.py`: single brief → no promotion, two briefs same theme → promotion, three briefs different themes → multi promotion, hypothesis backfill.

- [ ] **Step 6:** Commit: `add: theme promotion and hypothesis scope_theme_ids backfill at consolidate`.

---

## Task 10: Hypotheses API + UI

- [ ] **Step 1:** Add `services/api/app/schemas/hypotheses.py` with `HypothesisPublic`, `HypothesisListResponse`, query params.

- [ ] **Step 2:** Add `services/api/app/api/routes/hypotheses.py`:

  - `GET /api/research/hypotheses?state=&cursor=&limit=` — paginated, `created_at desc`.
  - `POST /api/research/hypotheses/{id}/activate` — proposed → active. 409 if not proposed; 404 if missing.

- [ ] **Step 3:** Mount the router in `app/main.py`.

- [ ] **Step 4:** Regenerate OpenAPI + `apps/web/lib/api/schema.ts`.

- [ ] **Step 5:** Add `apps/web/app/(app)/research/hypotheses/page.tsx` with filter dropdown (state) and list. Use existing data-fetch patterns.

- [ ] **Step 6:** Add `apps/web/components/research/hypothesis-row.tsx` with claim text, state badge, source run link, evidence count, activate button when state is `proposed`.

- [ ] **Step 7:** Add server action `actions.ts::activateHypothesis(id)`.

- [ ] **Step 8:** Tests:

  - Backend: `tests/test_hypotheses_api.py` covering list/filter/pagination, activate success/409/404.
  - Frontend tests deferred to Task 12.

- [ ] **Step 9:** Commit: `add: hypotheses list api, activate endpoint, research hypotheses page`.

---

## Task 11: Prompt Iteration Harness

- [ ] **Step 1:** Add `services/api/prompts/cases/` directory with at least one case file (`macro_brief_baseline.json`).

- [ ] **Step 2:** Add `app/services/strategies/funnel_research/_eval_harness.py`:

  - Load cases.
  - Iterate over prompt versions exported by `_prompts.py` (and any sector prompt registry).
  - Use a `DeterministicLlmClient` test double that hashes the messages and returns a fixed fixture; output records diff vs. expected.
  - Write JSONL to `.context/prompt-evals/<utc-iso>.jsonl`.

- [ ] **Step 3:** Add CLI script `services/api/scripts/run_prompt_evals.py` invoking the harness.

- [ ] **Step 4:** Add `tests/test_eval_harness.py` running the harness against a fixture case, asserting file is written and content shape.

- [ ] **Step 5:** Commit: `add: prompt iteration harness with cases, deterministic mock client, jsonl output`.

---

## Task 12: Frontend Tests (Vitest + RTL + Playwright)

- [ ] **Step 1:** Add devDependencies to `apps/web/package.json`: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `@playwright/test`. Pin to versions current at session date (resolve via `pnpm` registry, do not invent).

- [ ] **Step 2:** Add `apps/web/vitest.config.ts` and `apps/web/test/setup.ts` (jsdom + jest-dom matchers).

- [ ] **Step 3:** Add tests:

  - `apps/web/tests/run-summary-label.test.tsx` — funnel run label renders `MACRO · US EQUITIES`.
  - `apps/web/tests/macro-brief-detail.test.tsx` — renders themes, sector calls, judge badge, sector brief cards from canned fixture.
  - `apps/web/tests/sector-brief-card.test.tsx` — direction badge, conviction bar, evidence link.
  - `apps/web/tests/hypothesis-row.test.tsx` — activate button visible when proposed, hidden when active.

- [ ] **Step 4:** Add `apps/web/playwright.config.ts` configured to skip auto-starting the dev server (per CLAUDE.md). The test reads `BASE_URL` from env; CI/manual provides the running app.

- [ ] **Step 5:** Add `apps/web/e2e/macro-run-detail.spec.ts` smoke test:
  - Navigates to a fixture run id served by a mock route (`/api/research/runs/<id>/macro-brief`).
  - Asserts: timeline shows 6 stage steps, judge badge present, ≥1 sector card visible, cited claim opens chunk lookup.

- [ ] **Step 6:** Update `apps/web/package.json` scripts: `test`, `test:watch`, `e2e:smoke`.

- [ ] **Step 7:** Verify: `pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web build && pnpm --filter web test`. The e2e smoke is manual (no server auto-start).

- [ ] **Step 8:** Commit: `add: vitest setup, component tests for macro and sector and hypothesis, playwright macro run detail smoke`.

---

## Final Gates

- [ ] Backend: `pytest -q` green, `ruff check`, `mypy app`, Alembic round-trip clean.
- [ ] Frontend: `pnpm --filter web typecheck`, `lint`, `build`, `test` green. `e2e:smoke` documented as manual.
- [ ] OpenAPI + schema regeneration committed (no diff against running app).
- [ ] Each numbered task reviewed by the review agent before the next begins.
- [ ] No new unrelated files staged. `apps/web/next-env.d.ts` modifications and `services/api/uv.lock` remain outside Phase 5 commits unless separately verified and discussed with the user.

## Assumptions

- Phase 5 is intentionally broad; commits land in the order above, each one green on its own.
- Existing `tradingagents` behavior and event wire shape remain backward compatible.
- No Stage 3 company thesis, Stage 4 portfolio brief, autonomous agents, or full hypothesis lifecycle in this phase.
- Server-side dev/test runs do not require `npm run dev`; tests must work via headless modes only.
