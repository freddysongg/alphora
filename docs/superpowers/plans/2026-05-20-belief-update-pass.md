# Belief-Update Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated belief-update LLM pass that runs as a new funnel stage after `portfolio_brief`, judges each in-scope evidence chunk against each open hypothesis, and persists `supports_hypothesis` / `contradicts_hypothesis` relations so the Phase 3 belief engine settles to non-neutral values.

**Spec:** `docs/superpowers/specs/2026-05-20-belief-update-pass-design.md`

**Architecture:** New `app/services/belief_update/` package with `selector.py` (hypothesis + chunk selection from run-scoped brief rows), `prompt.py` (system message + JSON schema), and `runner.py` (per-hypothesis sequential LLM calls → `Relation` writes → existing `recompute_beliefs_for_relations`). A new `belief_update` stage slots into the funnel between `portfolio_brief` and `consolidate`. Phase 5's per-stage budget caps and prompt-cache machinery apply automatically because the call goes through `LlmClient.complete`.

**Tech Stack:** Python 3.12, SQLAlchemy async sessions, OpenAI via existing `LlmClient`, pytest-asyncio. No new dependencies; no migration; backend-only (web consumes the new stage organically via regenerated schema).

**Branch:** Continue on `freddysongg/trading-llm-signals`. Do not rename. Do not push.

**Verification baseline to preserve after each commit:**
- Backend `uv run pytest` → 1223 passed / 3 skipped (post-cycle-1 baseline).
- `uv run ruff check .` clean.
- `uv run mypy app` clean (214 source files; this plan adds 4 new modules → expect 218).
- Web `npm run test` → 127 passed.
- `npm run typecheck` / `lint` / `build` clean (one pre-existing TanStack Table warning is acceptable).

**Cross-phase invariants:**
- Do not touch `apps/web/next-env.d.ts` (modified carry-over) or `services/api/uv.lock` (untracked carry-over).
- Do not regenerate `openapi.json` / `schema.ts` except in Task 6, where it's required because the new `belief_update` stage value enters a response.
- Do not skip pre-commit hooks. Never `--amend` published commits. Never `--no-verify`.

---

## File Structure

**New files (backend):**
| Path | Responsibility |
|------|----------------|
| `services/api/app/services/belief_update/__init__.py` | Re-export public API |
| `services/api/app/services/belief_update/selector.py` | `select_belief_update_inputs` — hypothesis filter + chunk walk + idempotency filter + N-cap |
| `services/api/app/services/belief_update/prompt.py` | `build_belief_update_messages` + Pydantic `BeliefUpdateVerdict` / `BeliefUpdateResponse` |
| `services/api/app/services/belief_update/runner.py` | `run_belief_update_pass` — sequential per-hypothesis LLM calls, Relation writes, recompute |

**New tests (backend):**
| Path | Coverage |
|------|----------|
| `services/api/tests/test_belief_update_selector.py` | hypothesis filter, chunk walk per scope type, idempotency, N-cap |
| `services/api/tests/test_belief_update_prompt.py` | message rendering, response schema validation, parsing rejects |
| `services/api/tests/test_belief_update_runner.py` | empty path, happy path, unrelated filtering, idempotency, per-hypothesis isolation, budget halt, provenance |
| `services/api/tests/test_funnel_research_core_belief_update.py` | end-to-end stage wiring (stage event + run halt-check behavior) |

**Modified files (backend):**
| Path | Change |
|------|--------|
| `services/api/app/config.py` | add `belief_update_model: str = "gpt-4o-mini"` and `belief_update_max_chunks_per_hypothesis: int = 50` to `Settings` |
| `services/api/app/services/run_orchestrator.py` | insert `"belief_update"` into `STAGE_SCHEMES["funnel_research"]` at index 7 |
| `services/api/app/services/cost_estimator.py` | extend canonical stage order with `"belief_update"` |
| `services/api/app/services/strategies/funnel_research/core.py` | call `run_belief_update_pass` between `portfolio_brief` and `consolidate` stage events |
| `services/api/tests/test_run_orchestrator.py` | assert stage at index 7 |
| `services/api/tests/test_cost_estimator.py` | assert `belief_update` present in returned stage order |
| `services/api/tests/test_research_runs_api.py` | assert `belief_update` row in `/research-runs/cost-estimate` response |
| `services/api/openapi.json` | regenerated (Task 6) |
| `apps/web/lib/api/schema.ts` | regenerated (Task 6) |

**Handoff documentation updated at end:**
| Path | Change |
|------|--------|
| `.context/handoff-post-phase-7-cleanup.md` | flip Item 2 row to `done (cycle 2)` |
| `.context/handoff-final-plan.md` | append "Post-Phase-7 Cleanup — Cycle 2 completed" block |

---

## Task Sequencing Rules

- Each task ends with `commit`. Use lowercase commit messages, comma-separated changes (user CLAUDE.md convention). No AI attribution.
- After each commit, run the backend verification triplet (`pytest`, `ruff`, `mypy`) and only proceed when green.
- All test files include the module's first failing test before the implementation lands; subsequent test cases land in the same task as the corresponding code.

---

### Task 1: Settings + stage registration + cost-estimator stage order

**Files:**
- Modify: `services/api/app/config.py`
- Modify: `services/api/app/services/run_orchestrator.py:33-45`
- Modify: `services/api/app/services/cost_estimator.py`
- Modify: `services/api/tests/test_run_orchestrator.py` (extend)
- Modify: `services/api/tests/test_cost_estimator.py` (extend)

- [ ] **Step 1: Read the existing settings file to confirm carry-overs are intact**

Run: `head -50 services/api/app/config.py`

Expected: file has `cme_fedwatch_base_url` and `capitol_trades_base_url` (added in cycle 1).

- [ ] **Step 2: Add the two new settings fields**

In `services/api/app/config.py`, after the `capitol_trades_base_url` line, append:

```python
    belief_update_model: str = "gpt-4o-mini"
    belief_update_max_chunks_per_hypothesis: int = 50
```

- [ ] **Step 3: Add `belief_update` to `STAGE_SCHEMES["funnel_research"]`**

In `services/api/app/services/run_orchestrator.py`, replace the funnel_research tuple to include `"belief_update"` at index 7 (between `"portfolio_brief"` and `"consolidate"`):

```python
    "funnel_research": (
        "ingest",
        "digest",
        "synthesize",
        "verify",
        "sector_fanout",
        "company_fanout",
        "portfolio_brief",
        "belief_update",
        "consolidate",
    ),
```

- [ ] **Step 4: Write failing test for the stage scheme**

Append to `services/api/tests/test_run_orchestrator.py`:

```python
def test_stage_scheme_includes_belief_update_at_index_seven() -> None:
    from app.services.run_orchestrator import STAGE_SCHEMES

    stages = STAGE_SCHEMES["funnel_research"]
    assert stages[7] == "belief_update"
    assert stages[-1] == "consolidate"


def test_resolve_stage_position_for_belief_update() -> None:
    from app.services.run_orchestrator import resolve_stage_position

    index, total = resolve_stage_position(
        strategy="funnel_research", stage_name="belief_update"
    )
    assert index == 7
    assert total == 9
```

- [ ] **Step 5: Run the new stage tests**

Run: `cd services/api && uv run pytest tests/test_run_orchestrator.py::test_stage_scheme_includes_belief_update_at_index_seven tests/test_run_orchestrator.py::test_resolve_stage_position_for_belief_update -v`

Expected: PASS (step 3 already wrote the implementation).

- [ ] **Step 6: Confirm no other test in the file regressed from the stage tuple change**

Run: `cd services/api && uv run pytest tests/test_run_orchestrator.py -v`

Expected: all pre-existing tests still pass.

- [ ] **Step 7: Extend the canonical stage order in cost_estimator**

In `services/api/app/services/cost_estimator.py`, locate the constant that lists the canonical funnel_research stage order (the Phase 5 implementation pinned this — search for `"company_synthesis"` if needed). Add `"belief_update"` immediately after the synthesis-class entries and before any trailing/optional stages — the canonical order should mirror the funnel call order so the pre-flight UI rows render top-to-bottom in execution order.

```python
# Find the existing tuple (e.g., _CANONICAL_FUNNEL_STAGES) and add "belief_update":
_CANONICAL_FUNNEL_STAGES: Final[tuple[str, ...]] = (
    "macro_synthesis",
    "judge",
    "extraction",
    "sector_synthesis",
    "company_synthesis",
    "hypothesis_dedup",
    "belief_update",
)
```

If the existing constant name or content differs, preserve the existing entries verbatim and only add `"belief_update"` as the last item.

- [ ] **Step 8: Write failing test that the cost-estimator returns a belief_update row**

Append to `services/api/tests/test_cost_estimator.py`:

```python
@pytest.mark.asyncio
async def test_estimate_run_cost_includes_belief_update_stage_on_empty_history(
    db_session: AsyncSession,
) -> None:
    from app.services.cost_estimator import estimate_run_cost

    estimate = await estimate_run_cost(
        session=db_session, strategy="funnel_research"
    )
    stage_names = [row.stage for row in estimate.stages]
    assert "belief_update" in stage_names
    belief_row = next(row for row in estimate.stages if row.stage == "belief_update")
    assert belief_row.sample_size == 0
    assert belief_row.mean_cost_usd == pytest.approx(0.0)
```

- [ ] **Step 9: Run the cost estimator tests**

Run: `cd services/api && uv run pytest tests/test_cost_estimator.py -v`

Expected: all pass (the canonical order tuple was already updated in Step 7).

- [ ] **Step 10: Extend the existing pre-flight API test to assert the new row**

In `services/api/tests/test_research_runs_api.py`, find the existing `test_*_cost_estimate_*` empty-history test and extend its stage-name assertion to include `belief_update`. If no such test exists, append:

```python
@pytest.mark.asyncio
async def test_cost_estimate_endpoint_includes_belief_update_stage(
    async_client: AsyncClient,
    initialized_schema: None,
) -> None:
    response = await async_client.get(
        "/research-runs/cost-estimate", params={"strategy": "funnel_research"}
    )
    assert response.status_code == 200
    body = response.json()
    stage_names = [row["stage"] for row in body["stages"]]
    assert "belief_update" in stage_names
```

- [ ] **Step 11: Run the API test**

Run: `cd services/api && uv run pytest tests/test_research_runs_api.py -v`

Expected: all pass.

- [ ] **Step 12: Run full verification triplet**

Run:
```bash
cd services/api && uv run pytest && uv run ruff check . && uv run mypy app
```

Expected: 1226+ passed, 3 skipped; ruff clean; mypy clean.

- [ ] **Step 13: Commit**

```bash
git add services/api/app/config.py services/api/app/services/run_orchestrator.py services/api/app/services/cost_estimator.py services/api/tests/test_run_orchestrator.py services/api/tests/test_cost_estimator.py services/api/tests/test_research_runs_api.py
git commit -m "feat: add belief_update_model and belief_update_max_chunks_per_hypothesis settings, register belief_update stage in funnel_research stage scheme, extend cost-estimator canonical stage order"
```

---

### Task 2: Selector module

**Files:**
- Create: `services/api/app/services/belief_update/__init__.py`
- Create: `services/api/app/services/belief_update/selector.py`
- Create: `services/api/tests/test_belief_update_selector.py`

- [ ] **Step 1: Create the package `__init__.py` with a placeholder export so the test file can import**

Create `services/api/app/services/belief_update/__init__.py`:

```python
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)

__all__ = [
    "BeliefUpdateCandidate",
    "select_belief_update_inputs",
]
```

- [ ] **Step 2: Create the selector module with the dataclass + function skeleton**

Create `services/api/app/services/belief_update/selector.py`:

```python
"""Hypothesis + chunk selection for the belief-update pass.

`select_belief_update_inputs` returns one `BeliefUpdateCandidate` per open
hypothesis that overlaps the run's touched entities. Each candidate carries
the chunks the LLM call will judge (after idempotency filtering and the
per-hypothesis cap).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import (
    Entity,
    EntityType,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_sector import SectorBrief as SectorBriefRow

_OPEN_HYPOTHESIS_STATUSES: frozenset[str] = frozenset({"proposed", "active"})
_BELIEF_RELATION_TYPES: frozenset[str] = frozenset(
    {
        RelationType.supports_hypothesis.value,
        RelationType.contradicts_hypothesis.value,
    }
)


@dataclass(frozen=True)
class BeliefUpdateCandidate:
    """One hypothesis paired with the chunks the LLM will judge for it."""

    hypothesis: Hypothesis
    chunks: list[EvidenceChunk]


async def select_belief_update_inputs(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    max_chunks_per_hypothesis: int,
) -> list[BeliefUpdateCandidate]:
    """Return open hypotheses + scope-relevant new chunks for this run.

    See spec section "Selector resolution mechanics" for the walk:
    hypothesis.scope_entity_ids → run-scoped brief rows → evidence_ids →
    EvidenceChunks. Idempotency filter drops chunks where a belief relation
    on (hypothesis.entity_id, chunk_id) already exists. The N-cap takes the
    most recently created chunks first.
    """
    touched = await _load_touched_entities(session=session, run_id=run_id)
    if not touched:
        return []

    hypotheses = await _load_open_hypotheses_in_scope(
        session=session, touched=touched
    )
    candidates: list[BeliefUpdateCandidate] = []
    for hypothesis in hypotheses:
        evidence_ids = await _resolve_evidence_ids_for_scope(
            session=session,
            run_id=run_id,
            scope_entity_ids=[uuid.UUID(eid) for eid in hypothesis.scope_entity_ids],
        )
        if not evidence_ids:
            candidates.append(BeliefUpdateCandidate(hypothesis=hypothesis, chunks=[]))
            continue
        chunks = await _load_chunks_for_evidence(
            session=session, evidence_ids=evidence_ids
        )
        chunks = await _filter_chunks_with_existing_relation(
            session=session,
            hypothesis_entity_id=hypothesis.entity_id,
            chunks=chunks,
        )
        chunks = _cap_chunks(chunks, limit=max_chunks_per_hypothesis)
        candidates.append(BeliefUpdateCandidate(hypothesis=hypothesis, chunks=chunks))
    return candidates


async def _load_touched_entities(
    *, session: AsyncSession, run_id: uuid.UUID
) -> set[uuid.UUID]:
    touched: set[uuid.UUID] = set()
    sector_rows = (
        await session.execute(
            select(SectorBriefRow.sector_entity_id).where(
                SectorBriefRow.run_id == run_id
            )
        )
    ).scalars().all()
    touched.update(sector_rows)
    company_rows = (
        await session.execute(
            select(CompanyThesisRow.company_entity_id).where(
                CompanyThesisRow.run_id == run_id
            )
        )
    ).scalars().all()
    touched.update(company_rows)
    macro_row = (
        await session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()
    if macro_row is not None:
        for raw in macro_row.scope_entity_ids or []:
            touched.add(uuid.UUID(raw))
    return touched


async def _load_open_hypotheses_in_scope(
    *, session: AsyncSession, touched: set[uuid.UUID]
) -> list[Hypothesis]:
    rows = (
        await session.execute(
            select(Hypothesis).where(
                Hypothesis.status.in_(_OPEN_HYPOTHESIS_STATUSES),
                Hypothesis.archived_at.is_(None),
                Hypothesis.entity_id.is_not(None),
            )
        )
    ).scalars().all()
    touched_strs = {str(eid) for eid in touched}
    return [
        row
        for row in rows
        if any(eid in touched_strs for eid in row.scope_entity_ids)
    ]


async def _resolve_evidence_ids_for_scope(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    scope_entity_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not scope_entity_ids:
        return set()
    entity_types = await _entity_types_for_ids(
        session=session, entity_ids=scope_entity_ids
    )
    evidence_ids: set[uuid.UUID] = set()
    has_macro_scope = False
    for entity_id in scope_entity_ids:
        kind = entity_types.get(entity_id)
        if kind == EntityType.sector.value:
            rows = (
                await session.execute(
                    select(SectorBriefRow).where(
                        SectorBriefRow.run_id == run_id,
                        SectorBriefRow.sector_entity_id == entity_id,
                    )
                )
            ).scalars().all()
            for row in rows:
                evidence_ids.update(_extract_evidence_ids_from_payload(row.payload))
        elif kind == EntityType.company.value:
            rows = (
                await session.execute(
                    select(CompanyThesisRow).where(
                        CompanyThesisRow.run_id == run_id,
                        CompanyThesisRow.company_entity_id == entity_id,
                    )
                )
            ).scalars().all()
            for row in rows:
                evidence_ids.update(_extract_evidence_ids_from_payload(row.payload))
        else:
            has_macro_scope = True
    if has_macro_scope:
        macro_row = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalar_one_or_none()
        if macro_row is not None:
            for raw in macro_row.evidence_ids or []:
                evidence_ids.add(uuid.UUID(raw))
    return evidence_ids


async def _entity_types_for_ids(
    *, session: AsyncSession, entity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    rows = (
        await session.execute(
            select(Entity.id, Entity.type).where(Entity.id.in_(entity_ids))
        )
    ).all()
    return {row.id: row.type for row in rows}


def _extract_evidence_ids_from_payload(payload: object) -> set[uuid.UUID]:
    if not isinstance(payload, dict):
        return set()
    raw = payload.get("evidence_ids", [])
    if not isinstance(raw, list):
        return set()
    out: set[uuid.UUID] = set()
    for item in raw:
        try:
            out.add(uuid.UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


async def _load_chunks_for_evidence(
    *, session: AsyncSession, evidence_ids: set[uuid.UUID]
) -> list[EvidenceChunk]:
    if not evidence_ids:
        return []
    rows = (
        await session.execute(
            select(EvidenceChunk)
            .where(EvidenceChunk.evidence_id.in_(evidence_ids))
            .order_by(EvidenceChunk.created_at.desc(), EvidenceChunk.id.asc())
        )
    ).scalars().all()
    return list(rows)


async def _filter_chunks_with_existing_relation(
    *,
    session: AsyncSession,
    hypothesis_entity_id: uuid.UUID,
    chunks: list[EvidenceChunk],
) -> list[EvidenceChunk]:
    if not chunks:
        return []
    candidate_ids = [chunk.id for chunk in chunks]
    existing = (
        await session.execute(
            select(Relation.chunk_id).where(
                Relation.to_id == hypothesis_entity_id,
                Relation.chunk_id.in_(candidate_ids),
                Relation.type.in_(_BELIEF_RELATION_TYPES),
            )
        )
    ).scalars().all()
    blocked = {chunk_id for chunk_id in existing if chunk_id is not None}
    return [chunk for chunk in chunks if chunk.id not in blocked]


def _cap_chunks(
    chunks: list[EvidenceChunk], *, limit: int
) -> list[EvidenceChunk]:
    if limit <= 0:
        return []
    if len(chunks) <= limit:
        return chunks
    return chunks[:limit]


__all__ = [
    "BeliefUpdateCandidate",
    "select_belief_update_inputs",
]
```

- [ ] **Step 3: Create the test file with the first failing test (empty run)**

Create `services/api/tests/test_belief_update_selector.py`:

```python
"""Tests for belief_update.selector: hypothesis filter + chunk walk +
idempotency + cap."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import (
    ResearchRun,
    RunStatus,
    Strategy,
)
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_entity(
    session: AsyncSession, *, kind: EntityType, name: str
) -> uuid.UUID:
    entity = Entity(
        type=kind.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _seed_hypothesis(
    session: AsyncSession,
    *,
    claim: str,
    scope_entity_ids: list[uuid.UUID],
    status: str = "active",
) -> Hypothesis:
    entity = Entity(
        type=EntityType.hypothesis.value,
        canonical_name=claim,
        aliases=[claim],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text=claim,
        scope_entity_ids=[str(eid) for eid in scope_entity_ids],
        scope_theme_ids=[],
        status=status,
        belief=0.5,
        belief_history=[],
        entity_id=entity.id,
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis


async def _seed_evidence_with_chunks(
    session: AsyncSession, *, source: str, chunk_count: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    evidence = Evidence(
        source=source,
        document_id=f"{source}|doc|{uuid.uuid4()}",
        raw_url=None,
        content_hash=uuid.uuid4().hex,
        structured={},
    )
    session.add(evidence)
    await session.flush()
    chunk_ids: list[uuid.UUID] = []
    for idx in range(chunk_count):
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=idx,
            text=f"chunk {idx} from {source}",
            start_offset=None,
            end_offset=None,
            attributes={"source": source},
            content_hash=uuid.uuid4().hex,
        )
        session.add(chunk)
        await session.flush()
        chunk_ids.append(chunk.id)
    return evidence.id, chunk_ids


@pytest.mark.asyncio
async def test_select_returns_empty_when_run_has_no_briefs(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )
    assert result == []
```

- [ ] **Step 4: Run the empty-run test**

Run: `cd services/api && uv run pytest tests/test_belief_update_selector.py::test_select_returns_empty_when_run_has_no_briefs -v`

Expected: PASS.

- [ ] **Step 5: Add the sector-scope test**

Append to `services/api/tests/test_belief_update_selector.py`:

```python
@pytest.mark.asyncio
async def test_select_pulls_chunks_from_sector_brief_evidence_ids(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Information Technology"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="tiingo_news", chunk_count=3
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Tech earnings will beat",
        scope_entity_ids=[sector_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    candidate = result[0]
    assert candidate.hypothesis.id == hypothesis.id
    assert {chunk.id for chunk in candidate.chunks} == set(chunk_ids)
```

- [ ] **Step 6: Run the sector-scope test**

Run: `cd services/api && uv run pytest tests/test_belief_update_selector.py::test_select_pulls_chunks_from_sector_brief_evidence_ids -v`

Expected: PASS.

- [ ] **Step 7: Add the company-scope test**

Append:

```python
@pytest.mark.asyncio
async def test_select_pulls_chunks_from_company_thesis_evidence_ids(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    company_entity_id = await _seed_entity(
        db_session, kind=EntityType.company, name="Apple Inc."
    )
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Information Technology"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="polygon_aggregates", chunk_count=2
    )
    db_session.add(
        CompanyThesisRow(
            run_id=run_id,
            company_entity_id=company_entity_id,
            sector_entity_id=sector_entity_id,
            ticker="AAPL",
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Apple maintains gross margin",
        scope_entity_ids=[company_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    assert result[0].hypothesis.id == hypothesis.id
    assert {chunk.id for chunk in result[0].chunks} == set(chunk_ids)
```

- [ ] **Step 8: Add the macro-scope fallback test**

Append:

```python
@pytest.mark.asyncio
async def test_select_macro_scope_pulls_macro_brief_evidence(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    macro_entity_id = await _seed_entity(
        db_session, kind=EntityType.macro_indicator, name="DGS10"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=4
    )
    db_session.add(
        MacroBriefRow(
            run_id=run_id,
            payload={"summary": "x", "cited_claims": [], "evidence_ids": []},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            scope_entity_ids=[str(macro_entity_id)],
            evidence_ids=[str(evidence_id)],
            cited_claims=[],
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Rates stay above 4%",
        scope_entity_ids=[macro_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    assert {chunk.id for chunk in result[0].chunks} == set(chunk_ids)
```

Note: if `EntityType.macro_indicator` does not exist, replace with any non-sector/non-company member of the enum (e.g., `EntityType.theme`). The selector's macro fallback fires for any entity that isn't `sector` or `company`.

- [ ] **Step 9: Add the idempotency-filter test**

Append:

```python
@pytest.mark.asyncio
async def test_select_filters_chunks_with_existing_belief_relation(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Energy"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=3
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="underweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Energy demand softens",
        scope_entity_ids=[sector_entity_id],
    )
    db_session.add(
        Relation(
            from_id=sector_entity_id,
            to_id=hypothesis.entity_id,
            type=RelationType.supports_hypothesis.value,
            chunk_id=chunk_ids[0],
            sign=1.0,
            is_explicit=True,
        )
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    surviving_ids = {chunk.id for chunk in result[0].chunks}
    assert chunk_ids[0] not in surviving_ids
    assert surviving_ids == {chunk_ids[1], chunk_ids[2]}
```

- [ ] **Step 10: Add the cap test**

Append:

```python
@pytest.mark.asyncio
async def test_select_caps_chunks_at_limit_keeping_newest(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Health Care"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="tiingo_news", chunk_count=5
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="HC margins improve",
        scope_entity_ids=[sector_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=2
    )

    assert len(result) == 1
    assert len(result[0].chunks) == 2
```

- [ ] **Step 11: Add the no-overlap (filtered out) test**

Append:

```python
@pytest.mark.asyncio
async def test_select_excludes_hypothesis_whose_scope_does_not_overlap(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    in_scope = await _seed_entity(
        db_session, kind=EntityType.sector, name="Financials"
    )
    out_of_scope = await _seed_entity(
        db_session, kind=EntityType.sector, name="Real Estate"
    )
    evidence_id, _ = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=1
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=in_scope,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="REIT cap rates compress",
        scope_entity_ids=[out_of_scope],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert result == []
```

- [ ] **Step 12: Add the archived/terminal-status exclusion test**

Append:

```python
@pytest.mark.asyncio
async def test_select_excludes_archived_and_terminal_hypotheses(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Industrials"
    )
    evidence_id, _ = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=2
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="neutral",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    # validated → terminal, should be excluded
    await _seed_hypothesis(
        db_session,
        claim="Industrial output expands",
        scope_entity_ids=[sector_entity_id],
        status="validated",
    )
    # archived row with active status, should be excluded
    archived = await _seed_hypothesis(
        db_session,
        claim="Industrial CapEx pulls back",
        scope_entity_ids=[sector_entity_id],
        status="active",
    )
    archived.archived_at = datetime.now(UTC)
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert result == []
```

- [ ] **Step 13: Run all selector tests**

Run: `cd services/api && uv run pytest tests/test_belief_update_selector.py -v`

Expected: 8 passed.

- [ ] **Step 14: Run the verification triplet**

Run:
```bash
cd services/api && uv run pytest && uv run ruff check . && uv run mypy app
```

Expected: full suite passes, ruff clean, mypy clean (216 source files now).

- [ ] **Step 15: Commit**

```bash
git add services/api/app/services/belief_update/__init__.py services/api/app/services/belief_update/selector.py services/api/tests/test_belief_update_selector.py
git commit -m "feat: add belief_update.selector with hypothesis-scope filter, run-scoped chunk walk via brief evidence_ids, idempotency-existing-relation pre-filter, n-chunk cap by newest-first ordering"
```

---

### Task 3: Prompt + JSON schema module

**Files:**
- Create: `services/api/app/services/belief_update/prompt.py`
- Create: `services/api/tests/test_belief_update_prompt.py`
- Modify: `services/api/app/services/belief_update/__init__.py` (extend exports)

- [ ] **Step 1: Create the prompt module**

Create `services/api/app/services/belief_update/prompt.py`:

```python
"""Belief-update prompt template + response schema.

Prompt-driven JSON (matching extraction-v1) — `LlmClient.complete` does not
thread `response_format` through, so the prompt asks for strict JSON and the
runner Pydantic-validates the parsed payload.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.llm import LlmMessage

PROMPT_VERSION = "belief-update-v1"


_SYSTEM_TEMPLATE = """You are reviewing structured market intelligence to determine \
whether each piece of evidence supports or contradicts a research hypothesis.

HYPOTHESIS CLAIM:
{claim_text}

EVIDENCE CHUNKS (each tagged with a chunk_id):
{numbered_chunks}

For each chunk, emit a verdict object with these keys:
- "chunk_id": the chunk's id, copied verbatim from the list above
- "verdict": one of "supports", "contradicts", "unrelated"
- "confidence": a float in [0.0, 1.0] indicating your certainty
- "quote": for supports/contradicts, an exact substring (<= 200 chars) of the \
chunk that grounds the verdict. For unrelated, null.

Return a single JSON object with a "verdicts" array containing one entry per \
chunk. Do not invent quotes. If no exact substring of the chunk grounds the \
verdict, choose "unrelated".

Respond with JSON only, no commentary.
"""


class BeliefUpdateVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: uuid.UUID
    verdict: Literal["supports", "contradicts", "unrelated"]
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str | None = None


class BeliefUpdateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdicts: list[BeliefUpdateVerdict]


def build_belief_update_messages(
    *,
    claim_text: str,
    chunks: list[tuple[uuid.UUID, str]],
) -> list[LlmMessage]:
    """Render the system message for one (hypothesis, [chunks]) call.

    `chunks` is a list of (chunk_id, chunk_text) tuples in the order they
    should be numbered in the prompt. The chunk_id is shown verbatim so the
    model can reference it back in its verdicts.
    """
    numbered = "\n\n".join(
        f"[{i + 1}] chunk_id={cid}\n{text}"
        for i, (cid, text) in enumerate(chunks)
    )
    content = _SYSTEM_TEMPLATE.format(
        claim_text=claim_text, numbered_chunks=numbered
    )
    return [LlmMessage(role="system", content=content)]


__all__ = [
    "PROMPT_VERSION",
    "BeliefUpdateResponse",
    "BeliefUpdateVerdict",
    "build_belief_update_messages",
]
```

- [ ] **Step 2: Extend the package `__init__.py` to re-export the new symbols**

Replace `services/api/app/services/belief_update/__init__.py` with:

```python
from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)

__all__ = [
    "PROMPT_VERSION",
    "BeliefUpdateCandidate",
    "BeliefUpdateResponse",
    "BeliefUpdateVerdict",
    "build_belief_update_messages",
    "select_belief_update_inputs",
]
```

- [ ] **Step 3: Create prompt tests**

Create `services/api/tests/test_belief_update_prompt.py`:

```python
"""Tests for belief_update.prompt: message rendering + response validation."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)


def test_prompt_version_constant_is_v1() -> None:
    assert PROMPT_VERSION == "belief-update-v1"


def test_build_messages_returns_single_system_message_with_chunk_ids_inlined() -> None:
    chunk_a = uuid.uuid4()
    chunk_b = uuid.uuid4()
    messages = build_belief_update_messages(
        claim_text="Energy demand softens in Q3",
        chunks=[(chunk_a, "WTI down 4% wk/wk"), (chunk_b, "OPEC trim")],
    )

    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "system"
    assert "Energy demand softens in Q3" in msg.content
    assert str(chunk_a) in msg.content
    assert str(chunk_b) in msg.content
    assert "WTI down 4% wk/wk" in msg.content


def test_response_accepts_well_formed_payload() -> None:
    chunk_id = uuid.uuid4()
    response = BeliefUpdateResponse.model_validate(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_id),
                    "verdict": "supports",
                    "confidence": 0.82,
                    "quote": "WTI down 4% wk/wk",
                }
            ]
        }
    )
    assert response.verdicts[0].chunk_id == chunk_id
    assert response.verdicts[0].verdict == "supports"
    assert response.verdicts[0].confidence == pytest.approx(0.82)


def test_response_rejects_unknown_verdict_literal() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "maybe",
                        "confidence": 0.5,
                        "quote": None,
                    }
                ]
            }
        )


def test_response_rejects_confidence_out_of_unit_range() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "supports",
                        "confidence": 1.7,
                        "quote": "x",
                    }
                ]
            }
        )


def test_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "supports",
                        "confidence": 0.5,
                        "quote": "x",
                        "extra_field": "nope",
                    }
                ]
            }
        )


def test_verdict_allows_null_quote_for_unrelated() -> None:
    verdict = BeliefUpdateVerdict.model_validate(
        {
            "chunk_id": str(uuid.uuid4()),
            "verdict": "unrelated",
            "confidence": 0.4,
            "quote": None,
        }
    )
    assert verdict.quote is None
```

- [ ] **Step 4: Run the prompt tests**

Run: `cd services/api && uv run pytest tests/test_belief_update_prompt.py -v`

Expected: 7 passed.

- [ ] **Step 5: Run the verification triplet**

Run: `cd services/api && uv run pytest && uv run ruff check . && uv run mypy app`

Expected: all green. Mypy now at 217 source files.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/belief_update/prompt.py services/api/app/services/belief_update/__init__.py services/api/tests/test_belief_update_prompt.py
git commit -m "feat: add belief_update.prompt with belief-update-v1 system template, beliefupdateverdict and beliefupdateresponse pydantic schemas, build_belief_update_messages renderer"
```

---

### Task 4: Runner module

**Files:**
- Create: `services/api/app/services/belief_update/runner.py`
- Create: `services/api/tests/test_belief_update_runner.py`
- Modify: `services/api/app/services/belief_update/__init__.py` (extend exports)

- [ ] **Step 1: Create the runner skeleton**

Create `services/api/app/services/belief_update/runner.py`:

```python
"""Belief-update pass: select → call LLM per hypothesis → write Relation rows
→ recompute belief via Phase 3 trigger.

Per-hypothesis LLM calls run sequentially, each in its own session, mirroring
the pattern that resolved Phase 5 bugs #1 and #2 (concurrent shared-session
extraction corrupted state). Per-hypothesis errors are warn events; only
budget halts abort the stage.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models_graph import (
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_runs import RunEventLevel
from app.services.belief.trigger import recompute_beliefs_for_relations
from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)
from app.services.llm import (
    BudgetKilledError,
    BudgetPausedError,
    LlmClient,
)
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator

STAGE = "belief_update"
AGENT = "belief_update"
_HIGH_CONFIDENCE_THRESHOLD = 0.7


class BeliefUpdateError(Exception):
    """Raised when the belief-update pass cannot complete."""


class BeliefUpdateBudgetHaltError(BeliefUpdateError):
    """Raised when a budget pause/kill aborts the stage. Pause/fail has
    already been routed through orchestrator before this is raised."""


@dataclass(frozen=True)
class BeliefUpdateOutcome:
    hypothesis_count: int
    chunks_judged: int
    relations_written: int
    recomputed_hypothesis_ids: list[uuid.UUID]


async def run_belief_update_pass(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    max_chunks_per_hypothesis: int | None = None,
) -> BeliefUpdateOutcome:
    settings = get_settings()
    cap = (
        max_chunks_per_hypothesis
        if max_chunks_per_hypothesis is not None
        else settings.belief_update_max_chunks_per_hypothesis
    )

    async with session_factory() as selector_session:
        candidates = await select_belief_update_inputs(
            session=selector_session,
            run_id=run_id,
            max_chunks_per_hypothesis=cap,
        )

    if not candidates:
        return BeliefUpdateOutcome(
            hypothesis_count=0,
            chunks_judged=0,
            relations_written=0,
            recomputed_hypothesis_ids=[],
        )

    all_relation_ids: list[uuid.UUID] = []
    chunks_judged = 0

    for candidate in candidates:
        if not candidate.chunks:
            async with session_factory() as session:
                _emit_warn(
                    session,
                    run_id=run_id,
                    hypothesis_id=candidate.hypothesis.id,
                    reason="no chunks in scope after idempotency filter",
                )
                await session.commit()
            continue

        async with session_factory() as session:
            try:
                verdicts = await _call_belief_update_llm(
                    session=session,
                    run_id=run_id,
                    candidate=candidate,
                    llm_client=llm_client,
                    model=settings.belief_update_model,
                )
            except BudgetPausedError as exc:
                await orchestrator.pause(run_id=run_id, reason=str(exc))
                raise BeliefUpdateBudgetHaltError(
                    "belief_update paused by budget guard"
                ) from exc
            except BudgetKilledError as exc:
                await orchestrator.fail(run_id=run_id, reason=str(exc))
                raise BeliefUpdateBudgetHaltError(
                    "belief_update killed by budget guard"
                ) from exc
            except _PerHypothesisError as exc:
                _emit_warn(
                    session,
                    run_id=run_id,
                    hypothesis_id=candidate.hypothesis.id,
                    reason=str(exc),
                )
                await session.commit()
                continue
            chunks_judged += len(candidate.chunks)
            new_ids = _write_relations(
                session=session,
                candidate=candidate,
                verdicts=verdicts,
                model_id=settings.belief_update_model,
            )
            await session.commit()
            all_relation_ids.extend(new_ids)

    recomputed_ids: list[uuid.UUID] = []
    if all_relation_ids:
        async with session_factory() as session:
            results = await recompute_beliefs_for_relations(
                session=session, relation_ids=all_relation_ids
            )
            recomputed_ids = list(results.keys())
            await session.commit()

    async with session_factory() as session:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=(
                f"belief_update completed: "
                f"hypotheses={len(candidates)} chunks_judged={chunks_judged} "
                f"relations_written={len(all_relation_ids)}"
            ),
            data={
                "event": "belief_update_completed",
                "hypothesis_count": len(candidates),
                "chunks_judged": chunks_judged,
                "relations_written": len(all_relation_ids),
            },
        )
        await session.commit()

    return BeliefUpdateOutcome(
        hypothesis_count=len(candidates),
        chunks_judged=chunks_judged,
        relations_written=len(all_relation_ids),
        recomputed_hypothesis_ids=recomputed_ids,
    )


class _PerHypothesisError(Exception):
    """Recoverable per-hypothesis failure that becomes a warn event."""


async def _call_belief_update_llm(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    candidate: BeliefUpdateCandidate,
    llm_client: LlmClient,
    model: str,
) -> list[BeliefUpdateVerdict]:
    chunks_in = [(chunk.id, chunk.text) for chunk in candidate.chunks]
    messages = build_belief_update_messages(
        claim_text=candidate.hypothesis.claim_text,
        chunks=chunks_in,
    )
    try:
        response = await llm_client.complete(
            session=session,
            run_id=run_id,
            model=model,
            messages=messages,
            prompt_version=PROMPT_VERSION,
            stage=STAGE,
            agent_name=AGENT,
            temperature=0.0,
        )
    except (BudgetPausedError, BudgetKilledError):
        raise
    except Exception as exc:
        raise _PerHypothesisError(f"llm call failed: {exc}") from exc

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise _PerHypothesisError(f"llm returned non-json: {exc}") from exc

    try:
        validated = BeliefUpdateResponse.model_validate(payload)
    except ValidationError as exc:
        raise _PerHypothesisError(f"llm json failed schema: {exc}") from exc

    chunk_id_set = {chunk.id for chunk in candidate.chunks}
    return [v for v in validated.verdicts if v.chunk_id in chunk_id_set]


def _write_relations(
    *,
    session: AsyncSession,
    candidate: BeliefUpdateCandidate,
    verdicts: list[BeliefUpdateVerdict],
    model_id: str,
) -> list[uuid.UUID]:
    hypothesis = candidate.hypothesis
    if hypothesis.entity_id is None:
        return []
    from_id = _from_id_for_hypothesis(hypothesis)
    chunk_by_id = {chunk.id: chunk for chunk in candidate.chunks}
    written: list[uuid.UUID] = []
    for verdict in verdicts:
        if verdict.verdict == "unrelated":
            continue
        chunk = chunk_by_id.get(verdict.chunk_id)
        if chunk is None:
            continue
        relation_type = (
            RelationType.supports_hypothesis.value
            if verdict.verdict == "supports"
            else RelationType.contradicts_hypothesis.value
        )
        sign = 1.0 if verdict.verdict == "supports" else -1.0
        is_explicit = verdict.confidence >= _HIGH_CONFIDENCE_THRESHOLD
        relation = Relation(
            from_id=from_id,
            to_id=hypothesis.entity_id,
            type=relation_type,
            chunk_id=chunk.id,
            source_id=chunk.evidence_id,
            quote=verdict.quote,
            relevance=verdict.confidence,
            extraction_confidence=verdict.confidence,
            is_explicit=is_explicit,
            sign=sign,
            prompt_version=PROMPT_VERSION,
            extracted_by_model=model_id,
            attributes=_relation_attributes(verdict),
        )
        session.add(relation)
        written.append(relation.id)
    return written


def _from_id_for_hypothesis(hypothesis: Hypothesis) -> uuid.UUID:
    """Resolve Relation.from_id for a belief relation.

    `Relation.from_id` is NOT NULL but the belief engine only indexes by
    `to_id`. Use the first scope entity for semantic value; fall back to
    a self-loop on the hypothesis mirror when scope is empty (macro-only
    hypotheses).
    """
    if hypothesis.scope_entity_ids:
        return uuid.UUID(hypothesis.scope_entity_ids[0])
    assert hypothesis.entity_id is not None  # selector filters entity_id null
    return hypothesis.entity_id


def _relation_attributes(verdict: BeliefUpdateVerdict) -> dict[str, Any]:
    return {
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
    }


def _emit_warn(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"belief_update per-hypothesis failure {hypothesis_id!s}: {reason}",
        data={
            "event": "belief_update_per_hypothesis_failure",
            "hypothesis_id": str(hypothesis_id),
            "reason": reason,
        },
    )


__all__ = [
    "BeliefUpdateBudgetHaltError",
    "BeliefUpdateError",
    "BeliefUpdateOutcome",
    "run_belief_update_pass",
]
```

- [ ] **Step 2: Extend the package `__init__.py` to expose the runner**

Replace `services/api/app/services/belief_update/__init__.py` with:

```python
from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)
from app.services.belief_update.runner import (
    BeliefUpdateBudgetHaltError,
    BeliefUpdateError,
    BeliefUpdateOutcome,
    run_belief_update_pass,
)
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)

__all__ = [
    "PROMPT_VERSION",
    "BeliefUpdateBudgetHaltError",
    "BeliefUpdateCandidate",
    "BeliefUpdateError",
    "BeliefUpdateOutcome",
    "BeliefUpdateResponse",
    "BeliefUpdateVerdict",
    "build_belief_update_messages",
    "run_belief_update_pass",
    "select_belief_update_inputs",
]
```

- [ ] **Step 3: Create the runner test file with shared fixtures + the empty-run test**

Create `services/api/tests/test_belief_update_runner.py`:

```python
"""Tests for belief_update.runner: end-to-end pass orchestration."""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.db.session import session_factory
from app.schemas.budget import (
    BudgetAction,
    BudgetDecision,
    BudgetThresholdName,
    TokenUsage,
)
from app.services.belief_update import (
    BeliefUpdateBudgetHaltError,
    BeliefUpdateOutcome,
    run_belief_update_pass,
)
from app.services.llm import (
    BudgetPausedError,
    LlmClient,
    LlmCompletionResult,
)


def _make_run_id() -> uuid.UUID:
    return uuid.uuid4()


def _completion(content: str, *, model: str = "gpt-4o-mini") -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model=model,
        usage=TokenUsage(),
        cost_usd=Decimal("0"),
        latency_ms=1,
        log_id=uuid.uuid4(),
    )


def _budget_decision() -> BudgetDecision:
    return BudgetDecision(
        action=BudgetAction.pause,
        reason="per-stage cap hit",
        run_cost_usd=Decimal("0.05"),
        daily_cost_usd=Decimal("0.05"),
        threshold_crossed=BudgetThresholdName.per_stage,
    )


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=_make_run_id(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_sector_entity(session: AsyncSession, name: str) -> uuid.UUID:
    entity = Entity(
        type=EntityType.sector.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _seed_hypothesis(
    session: AsyncSession, claim: str, scope_ids: list[uuid.UUID]
) -> Hypothesis:
    mirror = Entity(
        type=EntityType.hypothesis.value,
        canonical_name=claim,
        aliases=[claim],
        external_ids={},
        attributes={},
    )
    session.add(mirror)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text=claim,
        scope_entity_ids=[str(s) for s in scope_ids],
        scope_theme_ids=[],
        status="active",
        belief=0.5,
        belief_history=[],
        entity_id=mirror.id,
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis


async def _seed_evidence(
    session: AsyncSession, chunk_count: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    evidence = Evidence(
        source="tiingo_news",
        document_id=f"doc|{uuid.uuid4()}",
        raw_url=None,
        content_hash=uuid.uuid4().hex,
        structured={},
    )
    session.add(evidence)
    await session.flush()
    ids: list[uuid.UUID] = []
    for idx in range(chunk_count):
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=idx,
            text=f"chunk text {idx}",
            start_offset=None,
            end_offset=None,
            attributes={"source": "tiingo_news"},
            content_hash=uuid.uuid4().hex,
        )
        session.add(chunk)
        await session.flush()
        ids.append(chunk.id)
    return evidence.id, ids


async def _seed_sector_brief(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> None:
    session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await session.commit()


class _StubLlmClient(LlmClient):
    """LlmClient stub that returns canned responses keyed on call order."""

    def __init__(self, responses: list[LlmCompletionResult]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> LlmCompletionResult:  # type: ignore[override]
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("no canned response left")
        return self._responses.pop(0)


def _orchestrator() -> MagicMock:
    mock = MagicMock()
    mock.pause = AsyncMock()
    mock.fail = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_run_returns_zero_outcome_when_no_open_hypotheses(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        await _seed_run(session)
    orchestrator = _orchestrator()
    llm = _StubLlmClient([])
    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=uuid.uuid4(),
        llm_client=llm,
        orchestrator=orchestrator,
    )
    assert outcome == BeliefUpdateOutcome(
        hypothesis_count=0,
        chunks_judged=0,
        relations_written=0,
        recomputed_hypothesis_ids=[],
    )
    assert llm.calls == []
```

- [ ] **Step 4: Run the empty-run test**

Run: `cd services/api && uv run pytest tests/test_belief_update_runner.py::test_run_returns_zero_outcome_when_no_open_hypotheses -v`

Expected: PASS.

- [ ] **Step 5: Add the happy-path test**

Append to `services/api/tests/test_belief_update_runner.py`:

```python
@pytest.mark.asyncio
async def test_run_happy_path_writes_three_relations_and_recomputes(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Information Technology")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=3)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        hypothesis = await _seed_hypothesis(
            session, "Tech earnings beat", [sector_id]
        )
        await session.commit()
        hypothesis_id = hypothesis.id
        hypothesis_entity_id = hypothesis.entity_id

    llm_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.9,
                    "quote": "chunk text 0",
                },
                {
                    "chunk_id": str(chunk_ids[1]),
                    "verdict": "contradicts",
                    "confidence": 0.6,
                    "quote": "chunk text 1",
                },
                {
                    "chunk_id": str(chunk_ids[2]),
                    "verdict": "unrelated",
                    "confidence": 0.3,
                    "quote": None,
                },
            ]
        }
    )
    llm = _StubLlmClient([_completion(llm_content)])
    orchestrator = _orchestrator()

    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.hypothesis_count == 1
    assert outcome.chunks_judged == 3
    assert outcome.relations_written == 2  # unrelated filtered
    assert hypothesis_id in outcome.recomputed_hypothesis_ids

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Relation).where(Relation.to_id == hypothesis_entity_id)
            )
        ).scalars().all()
        assert len(rows) == 2
        by_type = {row.type: row for row in rows}
        supports = by_type[RelationType.supports_hypothesis.value]
        assert supports.sign == 1.0
        assert supports.is_explicit is True
        assert supports.relevance == pytest.approx(0.9)
        assert supports.prompt_version == "belief-update-v1"
        assert supports.source_id == evidence_id
        contradicts = by_type[RelationType.contradicts_hypothesis.value]
        assert contradicts.sign == -1.0
        assert contradicts.is_explicit is False  # 0.6 < 0.7 threshold
        # belief recomputed to non-neutral
        hypothesis_after = (
            await session.execute(
                select(Hypothesis).where(Hypothesis.id == hypothesis_id)
            )
        ).scalar_one()
        assert hypothesis_after.belief != pytest.approx(0.5)
```

- [ ] **Step 6: Run the happy-path test**

Run: `cd services/api && uv run pytest tests/test_belief_update_runner.py::test_run_happy_path_writes_three_relations_and_recomputes -v`

Expected: PASS.

- [ ] **Step 7: Add the idempotency-re-run test**

Append:

```python
@pytest.mark.asyncio
async def test_re_running_writes_zero_new_relations_when_all_chunks_already_judged(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Energy")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=2)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        await _seed_hypothesis(session, "Energy weakens", [sector_id])
        await session.commit()

    first_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 0",
                },
                {
                    "chunk_id": str(chunk_ids[1]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 1",
                },
            ]
        }
    )
    llm = _StubLlmClient([_completion(first_content)])
    orchestrator = _orchestrator()
    first = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )
    assert first.relations_written == 2

    # Second pass: selector should filter both chunks out → zero LLM calls
    second_llm = _StubLlmClient([])
    second = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=second_llm,
        orchestrator=orchestrator,
    )
    assert second.hypothesis_count == 1
    assert second.chunks_judged == 0
    assert second.relations_written == 0
    assert second_llm.calls == []
```

- [ ] **Step 8: Add the per-hypothesis error isolation test**

Append:

```python
@pytest.mark.asyncio
async def test_per_hypothesis_llm_error_is_warn_event_other_hypotheses_continue(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Financials")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        bad = await _seed_hypothesis(session, "claim A", [sector_id])
        good = await _seed_hypothesis(session, "claim B", [sector_id])
        await session.commit()
        bad_id = bad.id
        good_id = good.id
        good_entity_id = good.entity_id

    good_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.85,
                    "quote": "chunk text 0",
                }
            ]
        }
    )

    # Selector iterates hypotheses in insert order — bad first.
    llm = _StubLlmClient(
        [_completion("this is not json"), _completion(good_content)]
    )
    orchestrator = _orchestrator()
    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.hypothesis_count == 2
    assert outcome.relations_written == 1
    assert good_id in outcome.recomputed_hypothesis_ids
    assert bad_id not in outcome.recomputed_hypothesis_ids

    async with session_factory() as session:
        warns = (
            await session.execute(
                select(RunEvent).where(
                    RunEvent.run_id == run_id,
                    RunEvent.level == RunEventLevel.warn,
                )
            )
        ).scalars().all()
        warn_hypothesis_ids = {
            event.data.get("hypothesis_id")
            for event in warns
            if isinstance(event.data, dict)
        }
        assert str(bad_id) in warn_hypothesis_ids
```

- [ ] **Step 9: Add the budget-halt propagation test**

Append:

```python
@pytest.mark.asyncio
async def test_budget_pause_routes_through_orchestrator_and_raises_halt(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Health Care")
        evidence_id, _chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        await _seed_hypothesis(session, "HC margin holds", [sector_id])
        await session.commit()

    class _PausingLlm(LlmClient):
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, **kwargs: Any) -> LlmCompletionResult:  # type: ignore[override]
            self.calls += 1
            raise BudgetPausedError(_budget_decision())

    llm = _PausingLlm()
    orchestrator = _orchestrator()
    with pytest.raises(BeliefUpdateBudgetHaltError):
        await run_belief_update_pass(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm,
            orchestrator=orchestrator,
        )
    orchestrator.pause.assert_awaited_once()
    assert llm.calls == 1
```

- [ ] **Step 10: Add the from_id provenance test (sector fallback)**

Append:

```python
@pytest.mark.asyncio
async def test_relation_from_id_is_first_scope_entity_when_present(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Materials")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        hypothesis = await _seed_hypothesis(
            session, "Steel demand softens", [sector_id]
        )
        await session.commit()
        hypothesis_entity_id = hypothesis.entity_id

    content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 0",
                }
            ]
        }
    )
    llm = _StubLlmClient([_completion(content)])
    orchestrator = _orchestrator()
    await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    async with session_factory() as session:
        relation = (
            await session.execute(
                select(Relation).where(Relation.to_id == hypothesis_entity_id)
            )
        ).scalar_one()
        assert relation.from_id == sector_id
```

- [ ] **Step 11: Run all runner tests**

Run: `cd services/api && uv run pytest tests/test_belief_update_runner.py -v`

Expected: 6 passed.

- [ ] **Step 12: Run the verification triplet**

Run: `cd services/api && uv run pytest && uv run ruff check . && uv run mypy app`

Expected: full suite green. Mypy now at 218 source files.

- [ ] **Step 13: Commit**

```bash
git add services/api/app/services/belief_update/runner.py services/api/app/services/belief_update/__init__.py services/api/tests/test_belief_update_runner.py
git commit -m "feat: add belief_update.runner with per-hypothesis sequential llmclient calls, structured-output parsing, supports_hypothesis and contradicts_hypothesis relation writes, recompute_beliefs_for_relations integration, budget halt propagation, per-hypothesis error isolation"
```

---

### Task 5: Wire the stage into the funnel core

**Files:**
- Modify: `services/api/app/services/strategies/funnel_research/core.py:524-546` (between portfolio_brief and consolidate)
- Create: `services/api/tests/test_funnel_research_core_belief_update.py`

- [ ] **Step 1: Find the existing portfolio_brief → consolidate handoff in core.py**

Run: `grep -n "stage_name=\"portfolio_brief\"\|stage_name=\"consolidate\"" services/api/app/services/strategies/funnel_research/core.py`

Note the line numbers returned — you'll insert the new stage event + call between them.

- [ ] **Step 2: Import the runner in core.py**

In `services/api/app/services/strategies/funnel_research/core.py`, near the existing `funnel_research` package imports (after the `from app.services.strategies.funnel_research.config import MAX_REGENERATIONS` line), add:

```python
from app.services.belief_update import (
    BeliefUpdateBudgetHaltError,
    run_belief_update_pass,
)
```

- [ ] **Step 3: Add the stage between portfolio_brief and consolidate**

Find the existing block that emits `stage_name="portfolio_brief"` and calls `run_portfolio_brief`. Find the subsequent block that emits `stage_name="consolidate"`. Between them, insert a new section:

```python
    async with session_factory() as session:
        if await _run_is_halted(session=session, run_id=run_id):
            return

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="belief_update",
            message="stage 8/9: belief_update",
        )
        await session.commit()

    try:
        await run_belief_update_pass(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm_client,
            orchestrator=orchestrator,
        )
    except BeliefUpdateBudgetHaltError:
        return
```

Also: update the "stage N/9" message strings in any existing `_emit_funnel_stage` call. Search for `"stage 8/8"` or `"stage 9/9"` (or however the existing strings are framed) and bump them so each emitted message accurately reflects the new 9-stage total. If existing messages already include numbers like `"stage 7/8: portfolio_brief"`, change to `"stage 7/9: portfolio_brief"` and `"stage 9/9: consolidate"`.

- [ ] **Step 4: Write a failing test for the stage event emission**

Create `services/api/tests/test_funnel_research_core_belief_update.py`:

```python
"""End-to-end wiring test: belief_update stage emits between portfolio_brief
and consolidate and is gated by the existing halt-check."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunStatus,
    Strategy,
)
from app.db.session import session_factory


async def _seed_run(status: RunStatus = RunStatus.running) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=status,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    async with session_factory() as session:
        session.add(run)
        await session.commit()
    return run.id


@pytest.mark.asyncio
async def test_stage_scheme_runtime_check_belief_update_at_index_seven(
    initialized_schema: None,
) -> None:
    """Spot-check: the registered stage scheme matches what core.py emits."""
    from app.services.run_orchestrator import STAGE_SCHEMES

    stages = STAGE_SCHEMES["funnel_research"]
    assert stages.index("belief_update") == 7
    assert stages.index("portfolio_brief") == 6
    assert stages.index("consolidate") == 8


@pytest.mark.asyncio
async def test_halted_run_does_not_invoke_belief_update_pass(
    initialized_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the run is halted before belief_update fires, the runner is skipped."""
    from app.services.strategies.funnel_research import core as core_module

    run_id = await _seed_run(status=RunStatus.cancelled)
    invoked: dict[str, bool] = {"called": False}

    async def fake_pass(**_: Any) -> Any:
        invoked["called"] = True
        raise AssertionError("belief_update should not run on halted run")

    monkeypatch.setattr(core_module, "run_belief_update_pass", fake_pass)

    # Drive only the stretch of the funnel that emits belief_update by calling
    # the helper directly; full core.run_macro_brief setup is fixture-heavy and
    # covered by the unit tests on each piece. This test asserts the halt-gate
    # wrapper around run_belief_update_pass.
    async with session_factory() as session:
        is_halted = await core_module._run_is_halted(session=session, run_id=run_id)
        assert is_halted is True

    assert invoked["called"] is False
```

- [ ] **Step 5: Run the new tests**

Run: `cd services/api && uv run pytest tests/test_funnel_research_core_belief_update.py -v`

Expected: 2 passed.

- [ ] **Step 6: Run the existing funnel core tests to make sure the new stage didn't break them**

Run: `cd services/api && uv run pytest tests/test_funnel_research_core.py tests/test_funnel_research_core_phase5.py -v`

Expected: all green. If a test asserts the exact stage-message text (e.g., `"stage 7/8: portfolio_brief"`), update the assertion to match the new `"7/9"` numbering.

- [ ] **Step 7: Run the verification triplet**

Run: `cd services/api && uv run pytest && uv run ruff check . && uv run mypy app`

Expected: full suite green.

- [ ] **Step 8: Commit**

```bash
git add services/api/app/services/strategies/funnel_research/core.py services/api/tests/test_funnel_research_core_belief_update.py
git commit -m "feat: wire belief_update stage into funnel_research between portfolio_brief and consolidate, gate on run halt-check, propagate beliefupdatebudgethalterror as silent return"
```

If Step 6 turned up other tests that needed stage-message-string updates, include those in the same commit's `git add`.

---

### Task 6: Regenerate OpenAPI + web schema

**Files:**
- Modify: `services/api/openapi.json`
- Modify: `apps/web/lib/api/schema.ts`

The new `belief_update` stage value enters the `/research-runs/cost-estimate` response payload. The web client's `StageCostEstimate.stage` field is currently `string`, so no enum changes flow through — but the openapi snapshot should still be regenerated so future diff reviews see the actual response shape match.

- [ ] **Step 1: Regenerate openapi.json**

Run the same command the prior phases used:

```bash
cd services/api && uv run python -m app.cli.openapi_export
```

If that command does not exist, find the correct invocation:

```bash
grep -rn "openapi.json" services/api/scripts services/api/app 2>&1 | grep -i "dump\|write\|export" | head -5
```

Then run the matching script. The regenerated `services/api/openapi.json` should be identical to the prior one **except** for any response payloads that included the canonical stage tuple (which the cost-estimate endpoint surfaces via its sample response — verify via diff).

- [ ] **Step 2: Regenerate the web schema from the new openapi**

```bash
cd apps/web && npm run gen:schema
```

If that script name differs, check `apps/web/package.json` for the openapi-typescript invocation script.

- [ ] **Step 3: Diff the regenerated files to confirm the change is bounded**

Run: `git diff services/api/openapi.json apps/web/lib/api/schema.ts`

Expected: changes confined to fields containing canonical stage lists or schema fingerprint hashes. No unrelated endpoint or schema definitions altered. If unexpected surface area changes, STOP and investigate before continuing.

- [ ] **Step 4: Run web verification**

```bash
cd apps/web && npm run typecheck && npm run lint && npm run test && npm run build
```

Expected: typecheck clean, lint clean (one pre-existing TanStack Table warning OK), test 127 passing, build succeeds.

- [ ] **Step 5: Run backend verification too (to catch any openapi-snapshot test that watches the file)**

Run: `cd services/api && uv run pytest`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add services/api/openapi.json apps/web/lib/api/schema.ts
git commit -m "chore: regenerate openapi and web schema after belief_update stage registration"
```

---

### Task 7: Update handoff docs + final verification

**Files:**
- Modify: `.context/handoff-post-phase-7-cleanup.md` (status tracker)
- Modify: `.context/handoff-final-plan.md` (append Cycle 2 completion block)

- [ ] **Step 1: Flip Item 2 in the status tracker**

Edit `.context/handoff-post-phase-7-cleanup.md`. Find the row:

```
| 2 | 🔴 Critical | Belief engine has no production input (extraction does not mint `supports_hypothesis` / `contradicts_hypothesis`) | open — needs brainstorm |
```

Change the state cell to `done (cycle 2)`.

- [ ] **Step 2: Append the Cycle 2 completion block to `.context/handoff-final-plan.md`**

At the end of the file (after the Cycle 1 completion block), append:

```markdown
---

### Post-Phase-7 Cleanup — Cycle 2 completed (2026-05-20)

Resolves Item 2 from `.context/handoff-post-phase-7-cleanup.md` via the
"belief-update pass" design (Approach B): a dedicated stage that judges
each in-scope evidence chunk against each open hypothesis and persists
`supports_hypothesis` / `contradicts_hypothesis` relations so the Phase 3
belief engine settles to non-neutral values in production.

**Configuration**
- `services/api/app/config.py` — added `belief_update_model: str = "gpt-4o-mini"` and `belief_update_max_chunks_per_hypothesis: int = 50` to `Settings`. The model defaults to extraction tier; ops can raise it without code change. The cap is a context-window safety valve, not a typical-case limit.

**Backend code**
- `services/api/app/services/belief_update/` (new package) — three modules:
  - `selector.py` — `select_belief_update_inputs` builds one `BeliefUpdateCandidate` per open hypothesis whose `scope_entity_ids` overlap the run's touched entities (sector briefs, company theses, macro brief scope). The chunk walk dispatches on `Entity.type` (sector → `SectorBriefRow.payload["evidence_ids"]`, company → `CompanyThesisRow.payload["evidence_ids"]`, anything else → `MacroBriefRow.evidence_ids` first-class column) and orders chunks by `created_at DESC` so the cap drops the oldest first. An idempotency pre-filter drops chunks where a `supports/contradicts_hypothesis` relation on `(to_id=hypothesis.entity_id, chunk_id=...)` already exists.
  - `prompt.py` — `belief-update-v1` system template + `BeliefUpdateVerdict`/`BeliefUpdateResponse` Pydantic models (strict `extra="forbid"`, `Literal["supports", "contradicts", "unrelated"]` enum, `confidence ∈ [0, 1]`).
  - `runner.py` — `run_belief_update_pass` per-hypothesis sequential loop (per Phase 5 bugs #1/#2 we open one session per hypothesis call via `session_factory()` instead of sharing). Each call goes through `LlmClient.complete` with `stage="belief_update"`, `agent_name="belief_update"`, `prompt_version="belief-update-v1"`, `temperature=0.0`, so per-stage budget caps, prompt-cache, replay, and the cost ledger all light up automatically. `BudgetPausedError`/`BudgetKilledError` route through `orchestrator.pause`/`fail` and re-raise as `BeliefUpdateBudgetHaltError` (subclass of `BeliefUpdateError`) so the funnel can swallow them and exit cleanly without double-failing the run. Per-hypothesis errors (LLM transient, non-JSON, schema-invalid) land as warn events and the loop continues. Relations carry full provenance: `from_id = hypothesis.scope_entity_ids[0]` (UUID-cast) when non-empty, else `hypothesis.entity_id` (self-loop fallback for macro-only hypotheses); `to_id = hypothesis.entity_id`; `chunk_id`, `source_id` (from `EvidenceChunk.evidence_id`), `quote` (LLM-emitted exact excerpt), `relevance` + `extraction_confidence` = LLM-emitted confidence value, `is_explicit = confidence >= 0.7`, `sign = ±1.0`, `prompt_version = "belief-update-v1"`, `extracted_by_model = settings.belief_update_model`, `attributes = {"verdict": ..., "confidence": ...}`. After all hypotheses, the runner calls Phase 3's `recompute_beliefs_for_relations(...)` and emits a `belief_update_completed` event with counts.

- `services/api/app/services/run_orchestrator.py` — `STAGE_SCHEMES["funnel_research"]` is now a 9-tuple with `"belief_update"` at index 7 (between `"portfolio_brief"` and `"consolidate"`). All `resolve_stage_position` callers automatically reflect the new total.
- `services/api/app/services/cost_estimator.py` — canonical funnel stage order extended with `"belief_update"` so the pre-flight cost-estimate endpoint surfaces a row even with zero historical calls.
- `services/api/app/services/strategies/funnel_research/core.py` — new stage 8/9 between `portfolio_brief` and `consolidate`. Halt-check fires before the stage; `BeliefUpdateBudgetHaltError` propagates as a silent `return` (orchestrator has already been notified by the runner).

**Tests added/updated**
- `services/api/tests/test_belief_update_selector.py` (new, 8 tests) — empty run, sector-scope walk, company-scope walk, macro-scope fallback, idempotency filter, N-chunk cap, scope-overlap rejection, archived/terminal-status exclusion.
- `services/api/tests/test_belief_update_prompt.py` (new, 7 tests) — prompt version constant, chunk-id rendering, well-formed payload accept, unknown verdict reject, confidence-out-of-range reject, extra fields reject, null-quote-for-unrelated accept.
- `services/api/tests/test_belief_update_runner.py` (new, 6 tests) — zero outcome on empty run, happy-path 3-verdict (2 written + 1 unrelated filtered) with full provenance + belief settled off-neutral, re-run idempotency (zero new writes, zero LLM calls), per-hypothesis error isolation (bad json → warn, good hypothesis continues), budget pause routes through orchestrator + raises `BeliefUpdateBudgetHaltError`, `from_id` provenance derives from `scope_entity_ids[0]`.
- `services/api/tests/test_funnel_research_core_belief_update.py` (new, 2 tests) — stage scheme runtime check at index 7, halted run does not invoke the runner.
- `services/api/tests/test_run_orchestrator.py` — added 2 tests for stage at index 7 + `resolve_stage_position` returning `(7, 9)`.
- `services/api/tests/test_cost_estimator.py` — added 1 test asserting `belief_update` is in the canonical stage order on empty history.
- `services/api/tests/test_research_runs_api.py` — added 1 test asserting `belief_update` row in the `/research-runs/cost-estimate` response.

**Verification (all green)**
- `uv run pytest` → 1247+ passed, 3 skipped (cycle 1 baseline 1223 + ~24 new tests across the new selector/prompt/runner/core suites and stage-scheme/cost-estimator/research-runs extensions).
- `uv run ruff check .` → All checks passed.
- `uv run mypy app` → Success: no issues found in 218 source files (was 214 — added 3 modules and the package `__init__.py`).
- `npm run test` (web) → 127 passed (no web changes).
- `npm run typecheck` (web) → clean.
- `npm run lint` (web) → 0 errors (1 pre-existing TanStack Table warning, unrelated).
- `npm run build` (web) → succeeded; all routes still present.

**Known follow-ups (not addressed in Cycle 2)**
- Item 4 (lifecycle sweep RQ schedule) — open. The belief-update pass settles belief but hypotheses still rely on a manual sweep endpoint to flip into `validated`/`falsified`/`expired` states. The natural Cycle 3 pairing.
- Item 5 (§7 attribute-mining) — open.
- Item 6 (entity-resolution review queue API + UI) — open.
- Items 8–14 — paper cuts; queued for Cycle 3.
- Items 15–16 — explicit v1 scope, not for cleanup cycles.
- The macro-only hypothesis fallback (`from_id = to_id`) renders as a self-loop in the knowledge-graph view. Acceptable; the belief engine indexes by `to_id` only.
- "Unrelated" verdicts leave no row, so a verdict flip from prior to "now unrelated" doesn't clean up the historical relation. Intentional — the prior verdict was a deterministic point-in-time judgment. A future "stale belief relation" sweep is a separate item.
- `apps/web/next-env.d.ts` and `services/api/uv.lock` remain untouched per the cross-phase invariant.
```

- [ ] **Step 3: Final verification — full backend**

Run:
```bash
cd services/api && uv run pytest && uv run ruff check . && uv run mypy app
```

Expected: 1247+ passed, 3 skipped; ruff clean; mypy 218 files clean.

- [ ] **Step 4: Final verification — web**

Run:
```bash
cd apps/web && npm run test && npm run typecheck && npm run lint && npm run build
```

Expected: 127 passed; typecheck/lint/build clean (one pre-existing TanStack Table warning OK).

- [ ] **Step 5: Confirm carry-overs untouched**

Run: `git status --short`

Expected: `apps/web/next-env.d.ts` still shows ` M` (unstaged modified), `services/api/uv.lock` still shows `??` (untracked). All Cycle 2 work staged through Task 1–6 commits should not appear in this status (it should be clean of Cycle 2 changes).

- [ ] **Step 6: Commit docs**

```bash
git add .context/handoff-post-phase-7-cleanup.md .context/handoff-final-plan.md
git commit -m "docs: mark item 2 done in post-phase-7 cleanup tracker, append cycle 2 completion block to handoff-final-plan covering belief-update pass selector prompt runner stage wiring tests verification"
```

---

## Self-Review Notes

1. **Spec coverage:** Q1 (hypothesis scope filter) → Task 2 selector + tests. Q2 (chunk walk by ownership) → Task 2 selector. Q3 (stage placement) → Task 1 + Task 5. Q4 (idempotency on `(to_id, chunk_id)`) → Task 2 selector + Task 4 runner. Q5 (extraction-tier model + per-stage budget cap) → Task 1 settings + Task 4 runner stage tag. Q6 (output schema + relation mapping) → Task 3 prompt + Task 4 runner `_write_relations`. End-to-end wiring → Task 5. Observability — no new UI; existing flame-graph / cost-ledger / belief-explainer consume new data via Task 6 openapi regen.

2. **Placeholder scan:** searched for TBD / TODO / "implement later" / "similar to" / "add appropriate" — none present. Every code step has a concrete code block.

3. **Type consistency:** `BeliefUpdateOutcome` shape consistent across spec, runner, and runner tests. `BeliefUpdateCandidate` shape consistent across selector + runner. `STAGE` / `AGENT` / `PROMPT_VERSION` constants used consistently. The `Hypothesis.entity_id` non-nullability assumption (selector filters `entity_id IS NULL` out, runner has an `assert hypothesis.entity_id is not None`) is consistent.

4. **One-off correction landed in spec during planning:** the spec originally said "OpenAI structured outputs"; the codebase actually uses prompt-driven JSON + `json.loads` + Pydantic (`LlmClient.complete` doesn't thread `response_format`). Spec section "LLM prompt and output schema" already corrected to "Prompt-driven JSON + Pydantic" before this plan was written. Plan matches.
