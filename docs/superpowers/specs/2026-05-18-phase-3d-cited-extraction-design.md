# Phase 3d — Cited Extraction + Deterministic Verifier

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-3d-cited-extraction` (off `origin/freddysongg/trading-llm-signals` @ `cbf3982`)
**Parallel coordination:** `docs/superpowers/phase-3-parallel-coordination.md`
**Spec section:** `.context/attachments/research-funnel-spec.md` §9 (extraction pipeline steps 3–4)
**Plan reference:** `.context/attachments/plan.md` Phase 3 item 3

## Goal

Take a single `EvidenceChunkRef` (from Phase 3b) and run the cheap-tier LLM extraction over it to produce candidate entities + relations, each carrying an `exact_quote` from the source chunk. A free regex verifier then rejects any candidate whose quote doesn't appear verbatim in the chunk text. The output is a typed `ExtractionResult`.

This is the **single highest-leverage hallucination control** in the project (spec §9). 80% of LLM hallucinations should be eliminated at zero LLM cost.

This is also the **first caller** of Phase 1's `app.services.llm.LlmClient`. Phase 3d owns the budget-error-to-orchestrator wiring.

## Non-Goals

- No entity resolution (3e).
- No DB writes for entities/relations. The output is a typed result; persisting candidates is downstream (3e's resolution step decides which become `entities` / `relations` rows).
- No new HTTP clients.
- No new migrations.
- No prompt engineering beyond a single v1 prompt template.
- No reasoning-model tier (spec §9 mentions "reserve reasoning model for ambiguous chunks"; v0 uses the cheap tier only).
- No batched extraction (one chunk per call).
- No API routes / SSE / UI.
- No 10-K-specific hierarchical extraction (out of scope — extraction prompt is source-type-agnostic for v0).

## Module Layout

```
services/api/app/services/extraction/
├── __init__.py              # public extract_from_chunk + ExtractionError
├── config.py                # extraction_model: str default "gpt-4o-mini", prompt_version: str default "extraction-v1"
├── _prompts.py              # build_extraction_messages() — system + user prompt templates
├── _verifier.py             # verify_candidates() — regex check that exact_quote is verbatim
├── _llm_call.py             # call_llm_for_extraction() — LlmClient caller + budget wiring
└── core.py                  # extract_from_chunk() — orchestrator that ties prompts + LlmClient + verifier

services/api/app/schemas/
└── extraction.py            # APPEND CandidateEntity, CandidateRelation, ExtractionResult

services/api/tests/
├── test_extraction_verifier.py        # exhaustive regex tests
├── test_extraction_prompts.py         # prompt construction snapshot
├── test_extraction_llm_call.py        # LlmClient interaction + budget errors
├── test_extraction_core.py            # end-to-end on a fixture chunk
└── test_extraction_schemas_candidates.py  # contract types
```

## Public API

```python
from app.services.extraction import extract_from_chunk, ExtractionError
from app.schemas.extraction import EvidenceChunkRef, ExtractionResult

result: ExtractionResult = await extract_from_chunk(
    session=session,            # passed to LlmClient for call-log persistence
    run_id=run_id,              # passed to LlmClient for budget tracking + orchestrator pause/fail
    chunk=evidence_chunk_ref,
)
```

The function returns an `ExtractionResult` always — even on verifier rejection, `verified=False` and `rejection_reasons` is populated. The caller (Phase 4's `FunnelResearchStrategy`) decides whether to persist the result or retry.

## Budget integration

Phase 3d is the first caller of `LlmClient.complete(...)`. The integration:

```python
try:
    response = await llm_client.complete(
        session=session,
        run_id=run_id,
        model=extraction_model,
        messages=messages,
        prompt_hash=prompt_hash,
        evidence_ids=[chunk.evidence_id],
    )
except BudgetPausedError as exc:
    await orchestrator.pause(run_id=run_id, reason=str(exc))
    raise ExtractionError("paused due to budget") from exc
except BudgetKilledError as exc:
    await orchestrator.fail(run_id=run_id, reason=str(exc))
    raise ExtractionError("killed due to budget") from exc
```

The orchestrator's `pause` and `fail` methods are imported from `app.services.run_orchestrator`. **Phase 3d does NOT modify `run_orchestrator.py`** — Phase 4 owns stage scheme. We only call the existing public methods.

Session ownership: per Phase 1 handoff, `LlmClient.complete` currently commits the caller-provided session. Phase 3d documents this in `_llm_call.py` and structures its session use accordingly: the LLM call gets its own transaction; the verifier and result assembly happen in-process without DB writes.

## Prompt design (v1)

`_prompts.py` produces an OpenAI Chat-Completions message list:

```
SYSTEM:
You are a structured-extraction assistant for financial / regulatory documents.
Output a JSON object with two keys: candidate_entities, candidate_relations.
Every entity and every relation MUST include an "exact_quote" field copied
VERBATIM from the source text. Do not paraphrase. Do not invent quotes.
If you cannot find a verbatim quote, omit the candidate.

USER:
Source chunk (chunk_id: {chunk_id}):
---
{chunk_text}
---

Extract entities and relations as JSON. Schema:
{
  "candidate_entities": [
    {
      "text_span": str,
      "suggested_type": one of [company, person, sector, country, product, regulator, bill, event, document, instrument, theme, hypothesis],
      "context_excerpt": str,
      "exact_quote": str,        // MUST appear verbatim in source chunk
      "extraction_confidence": float (0-1)
    }
  ],
  "candidate_relations": [
    {
      "subj_span": str,
      "predicate": one of [employs, holds_role_at, supplies, competes_with, regulated_by, traded_by, voted_on, sponsored, affects, belongs_to_sector, located_in, mentioned_in, catalyst_for, derives_from_theme, subsidiary_of, supports_hypothesis, contradicts_hypothesis],
      "obj_span": str,
      "exact_quote": str,        // MUST appear verbatim in source chunk
      "is_explicit": bool,
      "extraction_confidence": float (0-1)
    }
  ]
}

Reminder: every exact_quote MUST appear verbatim in the source chunk above.
```

The reminder appears at both start (system) and end (user) — positional redundancy per spec §9 "lost-in-the-middle mitigation."

The prompt is stored as a function returning the message list; `prompt_version="extraction-v1"` is set in `config.py`. `prompt_hash` for `LlmClient` logging is `sha256(serialized_messages).hexdigest()`.

## Deterministic verifier

`_verifier.py`'s job is to reject candidates whose `exact_quote` is not literally in `chunk.text`:

```python
def verify_candidates(
    *,
    chunk_text: str,
    candidate_entities: list[CandidateEntity],
    candidate_relations: list[CandidateRelation],
) -> VerifierResult:
    """Returns kept candidates and rejection reasons.
    A candidate's quote must appear as a literal substring of chunk_text,
    after whitespace normalization (collapse runs of whitespace to one space).
    """
```

Whitespace normalization detail: LLMs sometimes alter whitespace within copied quotes. We collapse runs of whitespace in both the chunk and the quote before comparing. Other character-level changes (capitalization, punctuation) are NOT tolerated — those count as hallucinations.

Rejection produces a structured reason: `"quote not in source: '...'"`.

A verifier counter-test: if the LLM outputs a quote with one substituted character, the verifier MUST reject. This is the headline property test.

## Contract types appended to `app/schemas/extraction.py`

Per coordination doc Contract 2:

```python
class CandidateEntity(BaseModel):
    model_config = ConfigDict(frozen=True)
    text_span: str
    suggested_type: EntityTypeEnum
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


class CandidateRelation(BaseModel):
    model_config = ConfigDict(frozen=True)
    subj_span: str
    predicate: RelationTypeEnum
    obj_span: str
    exact_quote: str
    chunk_id: uuid.UUID
    is_explicit: bool
    extraction_confidence: float


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    chunk_id: uuid.UUID
    candidate_entities: list[CandidateEntity]
    candidate_relations: list[CandidateRelation]
    model_id: str
    prompt_version: str
    verified: bool
    rejection_reasons: list[str]
```

Add the three names to `__all__` (alphabetically sorted).

## Configuration

`app/services/extraction/config.py`:

```python
from typing import Final

EXTRACTION_MODEL: Final[str] = "gpt-4o-mini"
PROMPT_VERSION: Final[str] = "extraction-v1"
MAX_RESPONSE_TOKENS: Final[int] = 4000
```

These are module-level constants, not pydantic-settings — 3f owns `app/config.py` and we don't want to race on it. Phase 4 can promote these to env-driven if needed.

## Test Strategy

- **Verifier tests** (`test_extraction_verifier.py`) — exhaustive. Cover:
  - Exact match: kept.
  - Whitespace runs in quote vs. chunk: kept.
  - One-character substitution: rejected with reason.
  - Quote completely fabricated: rejected.
  - Empty quote: rejected.
  - Quote with leading/trailing whitespace: kept (trimmed before compare).
  - Unicode normalization: rejected if the LLM substituted a fancy apostrophe for a straight one (canonical compare — no Unicode folding).
- **Prompt tests** (`test_extraction_prompts.py`) — snapshot the message list for a known chunk. Asserts both opening and closing reminders are present.
- **LLM call tests** (`test_extraction_llm_call.py`) — mock `LlmClient.complete` with a fake. Cover: happy path; `BudgetPausedError` → calls `orchestrator.pause` and raises `ExtractionError`; `BudgetKilledError` → calls `orchestrator.fail` and raises.
- **End-to-end tests** (`test_extraction_core.py`) — uses a fixed chunk + a hand-crafted JSON response (no real LLM). Asserts the result includes the candidates, marks `verified=True`, and the verifier passes through.
- **Verifier rejection end-to-end** — same shape but with a fabricated quote in the mock response. Asserts `verified=False` and `rejection_reasons` populated.

Target: ~25–35 new tests.

## Verification Gates

- `pytest`: ≥290 (261 baseline + new).
- `ruff check`: clean.
- `mypy app` strict: clean.

## Risks

| Risk | Mitigation |
|---|---|
| LLM returns malformed JSON | Use OpenAI's `response_format={"type": "json_object"}` (already supported by openai>=1.50). If still malformed, `ExtractionError`. |
| LLM doesn't actually copy quotes verbatim | The verifier catches this and rejects. That's the design. |
| `LlmClient.complete` session-commit behavior surprises caller | Document explicitly in `_llm_call.py`. Caller passes a session intended to be committed. Phase 4 owns the broader session lifecycle. |
| Orchestrator import causes a cycle | `app.services.run_orchestrator` doesn't import from `app.services.extraction` — no cycle. Verify on first mypy run. |
| The verifier's whitespace normalization is too lenient | Tests cover edge cases. If too lenient is observed in v0 runs, tighten in v1. |

## Out of scope (carried forward)

- Hierarchical extraction for 10-Ks (cheap-model outline pass + targeted second pass).
- Reasoning-tier model for ambiguous chunks.
- Batched extraction.
- Prompt iteration based on outcomes (v0 ships extraction-v1 only).
- Implicit/explicit relation classification with separate prompts.
