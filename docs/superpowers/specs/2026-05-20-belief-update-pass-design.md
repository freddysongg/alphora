# Belief-Update Pass — Design Spec

**Status:** approved (brainstormed 2026-05-20)
**Implements:** Item 2 from `.context/handoff-post-phase-7-cleanup.md`
**Spec source of truth:** §8 Belief Engine, §11 Hypothesis Lifecycle, in `.context/research-funnel-spec.md`

## Goal

Phase 3 wired the belief engine to consume `supports_hypothesis` / `contradicts_hypothesis` relations and compute `weighted_avg_decay_v1`. Phase 4 added the hypothesis lifecycle. Neither phase wired extraction (or any other path) to actually emit those relation kinds. Every hypothesis in production sits at the neutral 0.5 prior forever.

This design adds a dedicated belief-update LLM pass that runs as a new funnel stage after `portfolio_brief`, takes each open hypothesis and the run's scope-relevant evidence chunks, and asks the model whether each chunk supports or contradicts the hypothesis. Verdicts persist as `Relation` rows; the existing `recompute_beliefs_for_relations` (Phase 3) then settles belief on the affected hypotheses synchronously.

This is "Approach B" from the brainstorm — a separate belief-update pass over already-extracted evidence, decoupled from the general extraction prompt.

## Non-goals

- LLM-driven counterfactual perturbations (Item 15, v1 scope).
- End-to-end leakage runner (Item 16, v1 scope).
- Hypothesis-aware extraction prompt (rejected Approach A).
- Re-running belief judgments across historical runs (no schema for run-tagged belief relations).
- Backfilling belief relations against pre-existing extracted evidence from prior runs (out of scope; this pass handles the run it executes in).

## Brainstorm decisions (recap)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | Which hypotheses get processed | Open (`proposed` + `active`, `archived_at IS NULL`) whose `scope_entity_ids` overlap the run's touched entities |
| Q2 | Which evidence chunks the LLM sees | Chunks attached to evidence ingested under any of the hypothesis's scope entities (sector/company/macro ownership walk), capped at N=50 per call |
| Q3 | Stage placement in the funnel | New stage `belief_update` between `portfolio_brief` and `consolidate` |
| Q4 | Idempotency on re-run | De-dup on `(Relation.to_id, Relation.chunk_id)` — skip writing when a row already exists |
| Q5 | Model tier + cost guard | Extraction-grade model; register `belief_update` as a new `BudgetThresholds.per_stage_usd` key; route through existing `LlmClient.complete` |
| Q6 | Output schema + mapping | Prompt-driven JSON + Pydantic validate (matches extraction-v1); per-verdict mapping defined below |

## Architecture

### Module layout

```
services/api/app/services/belief_update/
├── __init__.py          # public API re-export
├── selector.py          # hypothesis + chunk selection
├── prompt.py            # prompt template + structured-output JSON schema
└── runner.py            # orchestrator (select → call LLM → write relations → recompute)
```

Co-located with `app/services/belief/` (Phase 3 — recompute pipeline) and `app/services/hypothesis/` (Phase 4 — lifecycle, dedup). The split keeps the recompute math (`belief/`) independent from the LLM-driven relation minting (`belief_update/`).

### Public API

```python
# services/api/app/services/belief_update/runner.py

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
    max_chunks_per_hypothesis: int = 50,
) -> BeliefUpdateOutcome
```

Called from `core.py` between the `portfolio_brief` and `consolidate` stage events, gated by the existing `_run_is_halted` check.

### Stage registration

`app/services/run_orchestrator.py:STAGE_SCHEMES["funnel_research"]` becomes a 9-tuple:

```python
"funnel_research": (
    "ingest",
    "digest",
    "synthesize",
    "verify",
    "sector_fanout",
    "company_fanout",
    "portfolio_brief",
    "belief_update",   # new
    "consolidate",
),
```

`app/services/cost_estimator.py` canonical stage order extended with `"belief_update"` so the pre-flight cost estimate UI surfaces a row even with zero historical calls.

## Algorithm

```
1. Load run's "touched entities":
   - sector_entity_ids from SectorBriefRow.sector_entity_id WHERE run_id=...
   - company_entity_ids from CompanyThesisRow.company_entity_id WHERE run_id=...
   - macro entity_ids from MacroBriefRow.scope_entity_ids WHERE run_id=...
   touched = sector_ids ∪ company_ids ∪ macro_ids

2. Halt-check: if _run_is_halted(run_id), return BeliefUpdateOutcome(0, 0, 0, []).

3. Open hypotheses:
   SELECT * FROM hypotheses
   WHERE status IN ('proposed', 'active')
     AND archived_at IS NULL
   -> Python-side filter: keep rows where any scope_entity_ids element ∈ touched
   (Python-side filter avoids SQLite vs Postgres JSON-array overlap differences.)

4. Per-hypothesis loop:
   a. Selector resolves hypothesis.scope_entity_ids → run-scoped brief rows →
      evidence_ids → chunks. See "Selector resolution mechanics" below.
   b. Filter: chunks where a (to_id=hypothesis.entity_id, chunk_id=this) belief
      relation already exists → drop (idempotency).
   c. Cap remaining chunks at max_chunks_per_hypothesis. When > cap, sort by
      chunk.created_at DESC and take the most recent (newest evidence first).
   d. If 0 chunks remain → emit warn event "belief_update_no_chunks_in_scope"
      with hypothesis_id and continue.
   e. LLM call via LlmClient.complete(...):
        stage="belief_update", agent_name="belief_update",
        prompt_version="belief-update-v1", temperature=0.0
      System message instructs the model to emit a strict JSON object with the
      schema documented in prompt.py. Caller does json.loads(response.content)
      and Pydantic-validates against BELIEF_UPDATE_RESPONSE_SCHEMA.
   f. Halt-check after each call. BudgetPausedError / BudgetKilledError from
      LlmClient propagate (caught by core.py and routed to orchestrator.pause /
      orchestrator.fail).
   g. For each non-"unrelated" verdict, build a Relation row (mapping below).
      Skip any verdict.chunk_id NOT in the chunks-passed-in set (defensive).
   h. Persist relations; collect their ids.

5. After all hypotheses processed:
   - recompute_beliefs_for_relations(session, relation_ids=all_written).
   - Emit "belief_update_completed" event with hypothesis_count, chunks_judged,
     relations_written.
   - Commit.
```

### Selector resolution mechanics

`Evidence` is global (no `run_id` column). To keep belief signals run-scoped, the selector walks via this run's brief tables:

- For each `scope_entity_id` on the hypothesis, query `Entity.type` to dispatch:
  - `sector` → load `SectorBriefRow` rows where `run_id = current_run_id AND sector_entity_id = scope_entity_id`. Extract `evidence_ids` from `row.payload["evidence_ids"]` (sector brief persists the full `SectorBriefPublic` in a JSON payload column, no first-class `evidence_ids` column).
  - `company` → load `CompanyThesisRow` rows where `run_id = current_run_id AND company_entity_id = scope_entity_id`. Extract `evidence_ids` from `row.payload["evidence_ids"]` (same JSON-payload convention).
  - Anything else (top-level macro entities, themes, broad-scope) → fall back to this run's `MacroBriefRow.evidence_ids` (a first-class column on the macro brief row, not a JSON payload field).
- Union all collected `evidence_ids` per hypothesis. Query `EvidenceChunk` where `evidence_id IN (...)`.
- Apply the idempotency filter (existing belief relation on `(to_id, chunk_id)`) and the N-chunk cap as described.

This walk is run-bounded because `SectorBriefRow.run_id` and `CompanyThesisRow.run_id` are real columns, so a hypothesis whose scope entity sat in a prior run's brief won't drag in stale chunks via this run's selector.

### Hypothesis filter — Python-side rationale

`Hypothesis.scope_entity_ids` is `JSON` (a Python list of UUID strings). SQLite test backend doesn't support `jsonb @> ?` operators. Postgres does, but writing two divergent code paths invites drift. The narrow `status IN (proposed, active) AND archived_at IS NULL` filter cuts the row count to per-run-relevant scale (~tens, not thousands), so a Python-side `any(eid in touched for eid in row.scope_entity_ids)` finishes in microseconds.

### Concurrency

Per-hypothesis LLM calls run **sequentially**. Phase 5 bugs #1 and #2 demonstrated that concurrent extraction with shared `AsyncSession` instances corrupts state. Each per-hypothesis call opens its own session via `session_factory()`. The extra I/O is negligible vs the LLM latency it gates.

### Per-hypothesis error isolation

Per-hypothesis LLM errors (parse failure, transient OpenAI error, etc.) become warn events with `event="belief_update_per_hypothesis_failure"`, `hypothesis_id=...`, `reason=...`. The loop continues. The only exceptions that abort the stage are `BudgetPausedError` and `BudgetKilledError` from `LlmClient.complete` — those propagate so the run pauses/fails cleanly.

## LLM prompt and output schema

### Prompt template (`belief-update-v1`)

```text
You are reviewing structured market intelligence to determine whether each
piece of evidence supports or contradicts a research hypothesis.

HYPOTHESIS CLAIM:
{claim_text}

EVIDENCE CHUNKS (each tagged with a chunk_id):
{numbered_chunks}

For each chunk, emit a verdict:
- "supports"     : the chunk's content increases confidence in the claim
- "contradicts"  : the chunk's content decreases confidence in the claim
- "unrelated"    : the chunk is neither for nor against the claim

For supports / contradicts verdicts, include an exact quote (≤ 200 chars)
from the chunk that grounds the verdict. For unrelated, set quote to null.

Confidence is your subjective certainty (0.0 to 1.0) that the verdict is
correct. Do not invent quotes. If no exact substring of the chunk grounds
a verdict, choose "unrelated".
```

### JSON output schema (Pydantic-validated)

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["verdicts"],
  "properties": {
    "verdicts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["chunk_id", "verdict", "confidence", "quote"],
        "properties": {
          "chunk_id": { "type": "string" },
          "verdict": { "type": "string", "enum": ["supports", "contradicts", "unrelated"] },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
          "quote": { "type": ["string", "null"] }
        }
      }
    }
  }
}
```

### Verdict → Relation mapping

| Verdict      | Action                                                              |
|--------------|---------------------------------------------------------------------|
| `supports`   | Write `Relation(type=supports_hypothesis, sign=+1.0)`              |
| `contradicts`| Write `Relation(type=contradicts_hypothesis, sign=-1.0)`           |
| `unrelated`  | Skip — no relation written                                          |

For every non-`unrelated` verdict:

| Relation field         | Value                                                                       |
|------------------------|-----------------------------------------------------------------------------|
| `from_id`              | `hypothesis.scope_entity_ids[0]` (UUID-cast) if non-empty, else `hypothesis.entity_id` (self-loop fallback for macro-only hypotheses) |
| `to_id`                | `hypothesis.entity_id` (the mirror)                                          |
| `type`                 | `supports_hypothesis` or `contradicts_hypothesis`                            |
| `chunk_id`             | the judged chunk's UUID                                                      |
| `source_id`            | `EvidenceChunk.evidence_id` lookup result                                    |
| `quote`                | the LLM-emitted exact excerpt                                                |
| `relevance`            | `verdict.confidence` (preserves continuous signal vs `1.0/0.6` heuristic)    |
| `extraction_confidence`| `verdict.confidence`                                                         |
| `is_explicit`          | `verdict.confidence >= 0.7` (heuristic)                                      |
| `sign`                 | `+1.0` for supports, `-1.0` for contradicts                                  |
| `prompt_version`       | `"belief-update-v1"`                                                         |
| `extracted_by_model`   | the model id reported by `LlmCompletionResult.model`                         |
| `attributes`           | `{"verdict": verdict, "confidence": confidence}` for downstream audit        |

## Configuration

### Settings

`app/config.py`:

```python
belief_update_model: str = "gpt-4o-mini"  # extraction-tier default
belief_update_max_chunks_per_hypothesis: int = 50
```

### Budget thresholds

`BudgetThresholds.per_stage_usd` (Phase 5) gets a new caller-defined key `"belief_update"`. Default cap left to operator; documented in the README + cycle 2 completion notes.

## Idempotency

The de-dup query, run per hypothesis before the LLM call:

```python
existing = select(Relation.chunk_id).where(
    Relation.to_id == hypothesis.entity_id,
    Relation.chunk_id.in_(candidate_chunk_ids),
    Relation.type.in_([
        RelationType.supports_hypothesis.value,
        RelationType.contradicts_hypothesis.value,
    ]),
)
```

`chunk_id`s in the result are removed from the candidate set. If the candidate set becomes empty after this filter, the LLM call is skipped entirely (no zero-verdict calls, no wasted tokens).

A defensive duplicate check is also performed before each individual relation insert in case of a concurrent re-run race. The same `(to_id, chunk_id, type)` triple is the de-dup key.

## Cost estimator

`cost_estimator.estimate_run_cost`'s canonical stage order extends to include `"belief_update"`. On a fresh deployment with no historical belief_update calls, the row surfaces with zero counts and zero cost. Once calls log to `llm_call_logs` with `stage="belief_update"`, the pre-flight estimate UI shows it organically — no UI changes required.

## Observability

The new stage flows through existing observability:

- **Cost ledger** (`aggregate_cost_ledger`): includes `belief_update` rows.
- **Run-timeline flame graph**: each per-hypothesis LLM call appears as a bar.
- **Cost meter SSE**: per-call cost events from `LlmClient` include the new stage.
- **Knowledge graph**: newly-written `supports/contradicts_hypothesis` relations appear as edges, signed-styled per the existing convention.
- **Belief explainer panel**: per-input breakdown table populates from the new relations via the existing `BeliefRecomputation.inputs` audit.

No new UI work is required for Item 2.

## Test plan

### Backend (`services/api/tests/`)

1. **`test_belief_update_selector.py`** — unit tests for selection:
   - hypothesis filter: status in {proposed, active}, archived_at null, scope overlap
   - chunk walk: sector ownership, company ownership, macro stage
   - idempotency filter: chunks with existing belief relations excluded
   - chunk cap respected (N=50 default; tested with monkeypatched limit)
   - macro-only hypothesis pulls macro stage chunks
   - hypothesis with no in-scope chunks returns empty list

2. **`test_belief_update_runner.py`** — orchestrator integration:
   - empty run (no open hypotheses) returns `BeliefUpdateOutcome(0, 0, 0, [])`
   - happy path: 1 hypothesis × 3 chunks → 3 relations, belief recomputed off-neutral
   - "unrelated" verdict is filtered (no relation written, no belief input contribution)
   - idempotency: re-running on the same data writes 0 new relations
   - per-hypothesis LLM error → warn event, others continue
   - budget halt propagates: `BudgetPausedError` from `LlmClient` re-raised
   - relation provenance: `from_id`, `to_id`, `chunk_id`, `quote`, `source_id`, `sign`, `relevance`, `is_explicit`, `prompt_version`, `extracted_by_model` all populated correctly per the mapping table
   - `from_id` fallback: macro-only hypothesis (empty scope_entity_ids) → `from_id == to_id` (self-loop)

3. **`test_funnel_research_core_belief_update.py`** — end-to-end funnel slice:
   - new `belief_update` stage event emitted between `portfolio_brief` and `consolidate`
   - belief_update stage runs after halt-check passes
   - halted run skips the stage cleanly

4. **`test_cost_estimator.py`** — extend existing tests:
   - `belief_update` appears in the canonical stage order returned by `estimate_run_cost`
   - zero historical calls → zero-row preserved (not dropped)
   - non-zero historical calls aggregated correctly

5. **`test_research_runs_api.py`** — extend existing tests:
   - `GET /research-runs/cost-estimate?strategy=funnel_research` includes a `belief_update` row

6. **`test_run_orchestrator.py`** — extend existing tests:
   - `STAGE_SCHEMES["funnel_research"]` includes `belief_update` at index 7
   - `resolve_stage_position(strategy="funnel_research", stage_name="belief_update")` returns `(7, 9)`

### Web (`apps/web/tests/`)

No new web tests. The existing cost-ledger, flame-graph, knowledge-graph, and belief-explainer components consume the new data automatically via the regenerated openapi schema.

### OpenAPI / schema regeneration

Required: yes. The new `belief_update` stage value extends the enum union in cost-estimator responses. Regenerate `services/api/openapi.json` and `apps/web/lib/api/schema.ts` and verify the existing stage filters in `cost-ledger.tsx` and `run-timeline-flame.tsx` accept the new value (they should — they accept arbitrary strings).

## Migration

Schema unchanged. No alembic migration required.

## Rollout

1. Land in a single PR after brainstorm + implementation plan approval.
2. Default `belief_update_max_chunks_per_hypothesis=50` is conservative — first prod runs will tune this if calls overflow context.
3. `belief_update_model` defaults to extraction-tier; operator can raise to a synthesis-tier model via Settings without code change.
4. The new stage adds latency to the funnel (per-hypothesis LLM call × N hypotheses). Estimate: 1–3 seconds per call × ~5–15 open hypotheses per run = 5–45 seconds added. Acceptable for a once-per-day macro run.

## Risks and known limits

- **N-chunk cap loses signal on hot sectors.** A sector with 100+ chunks gets the most recent 50; older chunks for the same hypothesis don't contribute belief signal until they age into a subsequent run. Mitigation: the cap is configurable; a follow-up could implement chunk-relevance ranking instead of recency.
- **Macro-only hypothesis fallback (`from_id = to_id`) is a self-loop.** Semantically odd but the belief engine indexes by `to_id` only — no downstream code reads `from_id` for belief computation. The graph view will render a self-loop edge, which is fine.
- **"Unrelated" verdicts are not persisted.** A model that flips its opinion between runs (related → unrelated) will not have the prior relation deleted. This is intentional — the prior verdict was a deterministic judgment at the time, and removing it would corrupt belief history. Future cleanup work (e.g., a "stale belief relation" sweep) is a separate item.
- **Per-hypothesis sequential calls add wall-clock latency.** Concurrency would shave this, but Phase 5 bugs make us cautious. If latency becomes a problem in production, the per-hypothesis sessions could be made truly independent via a session-per-task pattern like `extraction.py`.
- **The hypothesis "touched entities" filter is set-based.** A hypothesis with `scope_entity_ids` like `[sector_X]` is included if the run touches sector_X. But a hypothesis whose true semantic scope is broader (e.g., "interest rate hikes affect REITs") and whose `scope_entity_ids` is `[]` will never be in scope. Acceptable v0 limitation — the spec's intent is scope-narrowed runs anyway.

## Open questions / follow-ups

- Whether to deprecate the existing `1.0 explicit / 0.6 inferred` relevance heuristic and standardize on continuous confidence across all relation writers. Probably yes, but out of scope for Item 2.
- Whether to add a `belief_update.deltas` field on the run-detail UI showing "this run shifted hypothesis X's belief from 0.5 → 0.72". Nice-to-have; can land in Cycle 3 paper cuts.
- Item 12 (model tiers as config) lands after Item 2; the `belief_update_model` setting becomes a tier reference (`tier="low"`) once Item 12 ships.

## References

- `.context/handoff-post-phase-7-cleanup.md` — Item 2 specification.
- `.context/research-funnel-spec.md` — §8 Belief Engine, §11 Hypothesis Lifecycle.
- Phase 3 completion block in `.context/handoff-final-plan.md` — `weighted_avg_decay_v1` and `recompute_beliefs_for_relations` implementation.
- Phase 4 completion block in `.context/handoff-final-plan.md` — hypothesis lifecycle states, dedup, mirror-entity pattern.
- Phase 5 completion block — `BudgetThresholds.per_stage_usd`, `LlmClient.complete` budget halt path, cost estimator stage order.
- Phase 6 completion block — observability views that consume the new relations.
