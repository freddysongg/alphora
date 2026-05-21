# Phase 3e — Entity Resolution Pipeline

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-3e-entity-resolution` (off `origin/freddysongg/trading-llm-signals` @ `cbf3982`)
**Parallel coordination:** `docs/superpowers/phase-3-parallel-coordination.md`
**Spec section:** `.context/attachments/research-funnel-spec.md` §10 ("Entity resolution — the silent killer")
**Plan reference:** `.context/attachments/plan.md` Phase 3 item 5

## Goal

Implement the 5-step entity resolution pipeline that turns a `CandidateEntity` (from Phase 3d) into one of:

- A resolved `entities.id` (high-confidence match).
- A row in `entity_resolution_reviews` (low-confidence, queued for human review).
- A new `entities` row with `needs_review=true` (no plausible match — created fresh).

This pipeline is described in spec §10 as "the silent killer" — projects that get this wrong end up with duplicate entities, broken hypothesis traversals, and invisible underperformance.

## Non-Goals

- No LLM calls. Step 4 (LLM disambiguation) ships as a typed callable stub that defaults to "no decision." Phase 4 / Phase 5 wires real LLM disambiguation later.
- No entity creation outside the resolution pipeline.
- No entity merging. That's 3f's `merge_entities`.
- No relation persistence — that's downstream of resolution.
- No new tables, no migrations.
- No batch processing — the pipeline operates on one candidate at a time. Batch is a future optimization.
- No API routes / UI for the review queue.

## The 5-step pipeline (spec §10)

```
input: CandidateEntity (from 3d)

Step 1: Exact alias match
  entities.aliases contains candidate.text_span exactly?
  Unique hit → resolved (~80% of cases land here).

Step 2: External-ID match
  Does the surrounding context_excerpt contain a CIK / ticker / LEI / bioguide_id?
  Lookup by external_ids. Unique → resolved.

Step 3: Fuzzy match
  normalize_for_match(name) → lowercase, strip suffixes, trim
  rapidfuzz token_set_ratio against entities.canonical_name + aliases
  Threshold 0.85. Single high-confidence hit → resolved.
  Multiple candidates → Step 4.

Step 4: LLM disambiguation (stubbed in v0)
  Passes top-N fuzzy candidates + context to a callable.
  Default callable returns "no decision."
  If "no decision" or "none" → review queue.

Step 5: Create new entity → review queue
  Insert into entities with needs_review=true, confidence=extraction_confidence.
  Insert into entity_resolution_reviews with decision_kind=new_entity, status=pending.
```

## Module Layout

```
services/api/app/services/entity_resolution/
├── __init__.py                  # public resolve_candidate + ResolutionError
├── _normalize.py                # normalize_for_match() — shared with 3c's _normalize? See note below
├── _alias_match.py              # step_1_alias_match()
├── _external_id_match.py        # step_2_external_id_match()
├── _fuzzy_match.py              # step_3_fuzzy_match()
├── _llm_disambig.py             # step_4_llm_disambiguation() with stub callable
├── _create_new.py               # step_5_create_new_entity_with_review()
└── pipeline.py                  # resolve_candidate() — orchestrator running steps 1-5

services/api/tests/
├── test_entity_resolution_alias_match.py
├── test_entity_resolution_external_id_match.py
├── test_entity_resolution_fuzzy_match.py
├── test_entity_resolution_llm_disambig.py
├── test_entity_resolution_create_new.py
└── test_entity_resolution_pipeline.py        # end-to-end
```

**`_normalize.py` overlap with 3c:** 3c also has a `_normalize.py`. Two reasonable resolutions:
- (A) 3e re-implements its own — minor duplication, no cross-module dependency.
- (B) 3e imports from `app.services.entity_bootstrap._normalize` — slight cross-package coupling but DRY.

**Decision: option A.** 3e's normalization needs slightly different rules (lowercasing for comparison, not preserving case), and we don't want 3e's tests breaking when 3c tweaks its own normalization. Re-implement.

## Public API

```python
from app.services.entity_resolution import resolve_candidate, ResolutionError
from app.schemas.extraction import CandidateEntity, EntityResolutionOutcome

outcome: EntityResolutionOutcome = await resolve_candidate(
    session=session,
    candidate=candidate_entity,
    llm_disambiguator=None,  # optional; if None, uses stub
)
```

`llm_disambiguator` is the injection point for Phase 4's real LLM disambiguation. Its signature:

```python
LlmDisambiguator = Callable[
    [
        CandidateEntity,
        list[Entity],  # top-N fuzzy candidates
    ],
    Awaitable[uuid.UUID | None],  # chosen entity_id or None
]
```

## Step semantics

### Step 1 — Exact alias match

Find entities where `candidate.text_span IN entities.aliases`. Filter by `entities.merged_into_id IS NULL` (skip tombstones).

- 0 matches → fall through to Step 2.
- 1 match → resolved with `decision_kind=alias_match`, `confidence=0.95`.
- ≥2 matches → fall through to Step 2 (alias collisions across entities means the alias alone is ambiguous; need more signal).

### Step 2 — External-ID match

Scan `candidate.context_excerpt` for known external-ID patterns:

- `CIK` 10-digit: `\b0*\d{10}\b` (but only when "CIK" word is nearby)
- Ticker: `\b[A-Z]{1,5}\b` after "$" or near "(Nasdaq:" or "(NYSE:"
- LEI: 20-char alphanumeric: `\b[A-Z0-9]{20}\b`

For each match, look up `entities` where `external_ids` contains that key:value. Unique match → resolved with `decision_kind=external_id_match`, `confidence=0.99`.

Multiple matches → fall through (ambiguous).

This step is intentionally conservative — false positives are worse than false negatives because they create wrong-entity attribution. Only match when the pattern is strong.

### Step 3 — Fuzzy match

Normalize `candidate.text_span` (lowercase + strip suffixes + trim). Compute `rapidfuzz.token_set_ratio` against every entity's normalized canonical_name AND each alias.

**rapidfuzz is NOT currently a dependency.** Phase 3e adds it to `pyproject.toml`. Note: this is the only new runtime dependency across Phase 3b-3f.

Threshold: `0.85`. Take the top match.

- Top score < 0.85 → fall through to Step 4.
- Top score ≥ 0.85 AND second-best < 0.80 → resolved with `decision_kind=fuzzy_match`, `confidence = top_score`.
- Top score ≥ 0.85 AND second-best ≥ 0.80 → ambiguous; fall through to Step 4 (LLM disambiguation between top-N).

### Step 4 — LLM disambiguation (stubbed)

The injected `llm_disambiguator` callable is awaited if present, else a stub returns None. Stub policy: always return None ("no decision") in v0.

Real callable in Phase 4 will issue a cheap LLM call. The stub keeps the pipeline complete and testable today.

If disambiguator returns an `entity_id` → resolved with `decision_kind=llm_disambiguation`.
If returns `None` → fall through to Step 5.

### Step 5 — Create new entity → review queue

Insert a new `entities` row:
- `canonical_name = candidate.text_span`
- `type = candidate.suggested_type`
- `aliases = [candidate.text_span]`
- `external_ids = {}`
- `confidence = candidate.extraction_confidence`
- `needs_review = True`

Insert an `entity_resolution_reviews` row:
- `candidate_text = candidate.text_span`
- `suggested_type = candidate.suggested_type`
- `context_excerpt = candidate.context_excerpt`
- `decision_kind = new_entity`
- `candidate_entity_ids = []`
- `chosen_entity_id = <newly created entity id>`
- `status = pending`
- `confidence = candidate.extraction_confidence`

Return `EntityResolutionOutcome` with `decision_kind=new_entity`, `chosen_entity_id=<new>`, `review_id=<new>`.

## Contract type appended to `app/schemas/extraction.py`

Per coordination doc Contract 3:

```python
class EntityResolutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_text: str
    decision_kind: EntityResolutionDecisionKindEnum
    chosen_entity_id: uuid.UUID | None
    review_id: uuid.UUID | None
    confidence: float
```

Add `"EntityResolutionOutcome"` to `__all__` alphabetically.

## Test Strategy

- **Step 1 tests** — empty entities table → no match; one entity with alias → resolves; two entities both having the alias → ambiguous, falls through.
- **Step 2 tests** — regex patterns. Quote "Apple (Nasdaq: AAPL)" with an entity having `ticker=AAPL` → resolves. CIK pattern. LEI pattern. False-positive guard (just "AAPL" without ticker context → no match).
- **Step 3 tests** — rapidfuzz threshold honored. Single-good-match → resolves. Two-too-close-matches → falls through. Below threshold → falls through. Suffix stripping (`"Apple Inc."` matches `"Apple"`).
- **Step 4 tests** — stub returns None → falls through. Injected disambiguator returning a specific entity_id → resolved.
- **Step 5 tests** — new entity inserted with correct fields; review row inserted with correct decision_kind and status.
- **Pipeline end-to-end tests** — each step's hit path tested through the orchestrator with a populated entities table.

Target: ~25–35 new tests.

## Verification Gates

- `pytest`: ≥290 (261 baseline + new).
- `ruff check`: clean.
- `mypy app` strict: clean.
- `pyproject.toml`: new `rapidfuzz` runtime dependency MUST be added with a pinned major (e.g., `rapidfuzz>=3.0`).

## Risks

| Risk | Mitigation |
|---|---|
| Fuzzy matching at scale is slow (N entities × M chunks per run) | For Phase 3e v0, accept O(N) scan per call. Future: trigram index on `canonical_name` and `aliases`. |
| rapidfuzz adds a runtime dep | Pinned. Mature library, widely used. |
| Step 2 regex false positives (e.g., "AAPL" appearing in narrative text without ticker context) | Require "$" or "Nasdaq:" or similar disambiguator near the match. Tests cover false-positive cases. |
| LLM disambiguator stub is too permissive | "No decision" → always falls through to Step 5 (create new + review). Conservative by design. |
| Race condition: two concurrent resolutions for the same candidate text both create a new entity | Acceptable v0 noise; the merge mechanism in 3f resolves later. Document in code. |
| `entity_resolution_reviews` row inserted, then row in `entities` insertion fails | Wrap both in one transaction. If either fails, both roll back. |

## Out of scope (carried forward)

- LLM disambiguation real-callable (Phase 4).
- Trigram index in Postgres.
- Batch resolution.
- Reverse pipeline ("this entity should be split into two") — manual operation, not automated.
- Confidence calibration based on outcome stats.
- UI for the review queue.
