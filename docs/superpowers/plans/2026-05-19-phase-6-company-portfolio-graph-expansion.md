# Phase 6 - Company Thesis, Portfolio Brief, And Graph Workbench Implementation Plan

**Goal:** Add Stage 3 company thesis fan-out, Stage 4 portfolio brief, and richer graph UI surfaces while preserving the Phase 5 parent-run pipeline model.

**Spec:** `docs/superpowers/specs/2026-05-19-phase-6-company-portfolio-graph-expansion-design.md`
**Working directory:** `services/api/` for backend verification; `apps/web/` only when graph UI or generated web schemas are touched.
**Branch:** Continue on `freddysongg/trading-llm-signals`. Do not rename.

## Commit Order

1. **Docs:** Add Phase 6 spec and plan.
2. **Company schema foundation:** Add migration `007`, ORM model, schemas, and tests.
3. **Company selector contract:** Add `company/` package with selector and tests.
4. **Company evidence/extraction/graph:** Mirror sector source isolation, extraction orchestration, and candidate persistence.
5. **Company prompts/LLM/verifier/persist:** Add synthesis messages, LLM call wrapper, deterministic verifier, judge persistence.
6. **Company runner wiring:** Add `company_fanout` to the stage scheme and wire the runner between sector fan-out and portfolio brief.
7. **Portfolio brief:** Add one-row-per-run portfolio brief table, schema, deterministic or LLM synthesis, route, and tests.
8. **Graph UI surfaces:** Land entity browser, relation explorer, evidence flow, review queue, and contradiction view as independent slices.
9. **Carry-overs:** Redis worker limiter wiring, Playwright smoke automation, and eval harness expansion may land between larger slices when bounded.

## First Slice Details

- Add `company_theses` table with the same persistence pattern as `sector_briefs`.
- Add `CompanyThesis`, `CompanyCatalyst`, `CompanyRisk`, and `CompanyThesisPublic` schemas.
- Add `app/services/strategies/funnel_research/company/__init__.py`.
- Add `company/selector.py`:
  - `MAX_COMPANY_DEEP_DIVES = 5`
  - Select from persisted `SectorBriefPublic` objects.
  - Exclude neutral company ideas.
  - Sort by non-neutral direction first, conviction descending, sector name ascending, original company index ascending.
  - Deduplicate by uppercase ticker when present, otherwise by normalized company name.
  - Return frozen `CompanyIdea` records carrying company name, ticker, direction, conviction, sector metadata, evidence IDs, and original index.

## Later Stage 3 Slices

- Evidence uses EDGAR submissions, Ainvest congress/news data, Polygon aggregates, Tiingo prices/news, and graph context with per-source warn isolation.
- Extraction reuses `extract_from_chunk` under bounded concurrency and persists graph candidates only when endpoints resolve.
- Prompts use positional redundancy and require exact quotes for every cited claim.
- Verifier checks company name, company entity id, sector identity, cited chunk membership, and quote verbatim match.
- Runner uses bounded fan-out and fails the parent run only when selected companies are non-empty and every selected company fails.

## Test Plan

- First slice:
  - Alembic migration `007` upgrade/downgrade round trip.
  - ORM constraint/default tests for `company_theses`.
  - Schema validation tests for company thesis public payloads.
  - Selector tests for empty input, neutral filtering, ranking, cap, ties, and deduplication.
- Verification from `services/api/` before claiming completion:
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/python -m ruff check`
  - `.venv/bin/python -m mypy app`
  - `DATABASE_URL=sqlite+aiosqlite:///tmp/check.db .venv/bin/python -m alembic upgrade head`
  - `DATABASE_URL=sqlite+aiosqlite:///tmp/check.db .venv/bin/python -m alembic downgrade base`

## Assumptions

- Existing dirty files `apps/web/next-env.d.ts` and `services/api/uv.lock` stay unstaged.
- No dev servers are run.
- No push is performed.
- Web verification is required only for slices that touch `apps/web` or regenerate API schemas.
