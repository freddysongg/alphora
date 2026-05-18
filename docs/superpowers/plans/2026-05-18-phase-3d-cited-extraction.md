# Phase 3d — Cited Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cited extraction from one chunk at a time. Outputs typed `ExtractionResult` with candidate entities + relations, each carrying a verbatim `exact_quote`. Deterministic regex verifier rejects non-verbatim quotes. First caller of `LlmClient`.

**Architecture:** New `app/services/extraction/` sub-package. `extract_from_chunk()` ties prompts + `LlmClient` + verifier in sequence. Budget-error catches route to `orchestrator.pause` / `orchestrator.fail`. Appends `CandidateEntity`, `CandidateRelation`, `ExtractionResult` to `app/schemas/extraction.py`.

**Tech Stack:** OpenAI SDK (via `LlmClient`), Pydantic v2, regex stdlib. All existing deps.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3d-cited-extraction-design.md`
**Coordination:** `docs/superpowers/phase-3-parallel-coordination.md`

**Working dir:** `services/api/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/schemas/extraction.py` | Append `CandidateEntity`, `CandidateRelation`, `ExtractionResult` |
| `app/services/extraction/__init__.py` | Public `extract_from_chunk`, `ExtractionError` |
| `app/services/extraction/config.py` | Constants: `EXTRACTION_MODEL`, `PROMPT_VERSION`, `MAX_RESPONSE_TOKENS` |
| `app/services/extraction/_prompts.py` | `build_extraction_messages()` |
| `app/services/extraction/_verifier.py` | `verify_candidates()`, `VerifierResult` |
| `app/services/extraction/_llm_call.py` | `call_llm_for_extraction()` |
| `app/services/extraction/core.py` | `extract_from_chunk()` |
| `tests/test_extraction_schemas_candidates.py` | NEW |
| `tests/test_extraction_verifier.py` | NEW |
| `tests/test_extraction_prompts.py` | NEW |
| `tests/test_extraction_llm_call.py` | NEW |
| `tests/test_extraction_core.py` | NEW |

---

## Task 1: Append `CandidateEntity`, `CandidateRelation`, `ExtractionResult` to `app/schemas/extraction.py`

Wait for 3b to create the file. If not present, STOP.

- [ ] **Step 1: Failing test**

```python
# tests/test_extraction_schemas_candidates.py
import uuid

def test_candidate_entity_carries_exact_quote() -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import CandidateEntity

    candidate = CandidateEntity(
        text_span="Apple",
        suggested_type=EntityType.company,
        context_excerpt="Apple unveiled a new product",
        exact_quote="Apple",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.92,
    )
    assert candidate.exact_quote == "Apple"


def test_candidate_relation_has_predicate_enum() -> None:
    from app.db.models_graph import RelationType
    from app.schemas.extraction import CandidateRelation

    rel = CandidateRelation(
        subj_span="Apple",
        predicate=RelationType.regulated_by,
        obj_span="SEC",
        exact_quote="Apple files annual reports with the SEC",
        chunk_id=uuid.uuid4(),
        is_explicit=True,
        extraction_confidence=0.88,
    )
    assert rel.predicate == RelationType.regulated_by


def test_extraction_result_aggregates_candidates_with_verifier_flags() -> None:
    from app.schemas.extraction import ExtractionResult

    result = ExtractionResult(
        chunk_id=uuid.uuid4(),
        candidate_entities=[],
        candidate_relations=[],
        model_id="gpt-4o-mini",
        prompt_version="extraction-v1",
        verified=True,
        rejection_reasons=[],
    )
    assert result.verified is True


def test_extraction_module_all_includes_candidates() -> None:
    from app.schemas import extraction

    for name in ("CandidateEntity", "CandidateRelation", "ExtractionResult"):
        assert name in extraction.__all__
```

- [ ] **Step 2: Append to `app/schemas/extraction.py`**

Ensure imports at top include:

```python
from app.schemas.common import EntityTypeEnum, RelationTypeEnum
```

Append:

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

Add the 3 names to `__all__` alphabetically.

- [ ] **Step 3: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_extraction_schemas_candidates.py -v
.venv/bin/python -m ruff check app/schemas/extraction.py
.venv/bin/python -m mypy app/schemas/extraction.py
git add app/schemas/extraction.py tests/test_extraction_schemas_candidates.py
git commit -m "add candidate entity, candidate relation, and extraction result contracts"
```

---

## Task 2: Deterministic verifier (`_verifier.py`)

The most important piece. Exhaustive tests.

- [ ] **Step 1: Tests**

```python
# tests/test_extraction_verifier.py
import uuid

import pytest


def _candidate_entity(quote: str):
    from app.db.models_graph import EntityType
    from app.schemas.extraction import CandidateEntity

    return CandidateEntity(
        text_span="X",
        suggested_type=EntityType.company,
        context_excerpt="...",
        exact_quote=quote,
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


def _candidate_relation(quote: str):
    from app.db.models_graph import RelationType
    from app.schemas.extraction import CandidateRelation

    return CandidateRelation(
        subj_span="X",
        predicate=RelationType.affects,
        obj_span="Y",
        exact_quote=quote,
        chunk_id=uuid.uuid4(),
        is_explicit=True,
        extraction_confidence=0.9,
    )


def test_verifier_keeps_exact_match() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue in Q4."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple Inc.")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1
    assert result.rejection_reasons == []


def test_verifier_rejects_one_character_substitution() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue in Q4."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple lnc.")],  # lowercase L instead of I
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    assert "Apple lnc." in result.rejection_reasons[0]


def test_verifier_rejects_completely_fabricated_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Microsoft acquired LinkedIn")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


def test_verifier_rejects_empty_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    result = verify_candidates(
        chunk_text="anything",
        candidate_entities=[_candidate_entity("")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


def test_verifier_normalizes_whitespace_runs() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple    reported  record  revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple reported record revenue.")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_trims_quote_leading_trailing_whitespace() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("  Apple reported record revenue.  ")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_rejects_smart_quote_substitution() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "He said 'no comment' at the briefing."  # straight quotes
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("He said ‘no comment’ at the briefing.")],
        candidate_relations=[],
    )

    assert result.kept_entities == []


def test_verifier_verifies_relations_independently() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[_candidate_relation("Apple supplies chips to its data centers.")],
    )

    assert len(result.kept_relations) == 1


def test_verifier_separates_kept_and_rejected_in_mixed_input() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple released a new phone."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity("Apple released a new phone."),  # kept
            _candidate_entity("Microsoft launched a tablet."),  # rejected
        ],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1
    assert len(result.rejection_reasons) == 1
```

- [ ] **Step 2: Implement**

```python
# app/services/extraction/_verifier.py
import re
from dataclasses import dataclass

from app.schemas.extraction import CandidateEntity, CandidateRelation

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


@dataclass(frozen=True)
class VerifierResult:
    kept_entities: list[CandidateEntity]
    kept_relations: list[CandidateRelation]
    rejection_reasons: list[str]


def verify_candidates(
    *,
    chunk_text: str,
    candidate_entities: list[CandidateEntity],
    candidate_relations: list[CandidateRelation],
) -> VerifierResult:
    normalized_chunk = _normalize(chunk_text)

    kept_entities: list[CandidateEntity] = []
    kept_relations: list[CandidateRelation] = []
    rejections: list[str] = []

    for candidate in candidate_entities:
        quote = candidate.exact_quote
        normalized_quote = _normalize(quote)
        if not normalized_quote:
            rejections.append(f"empty quote on entity span={candidate.text_span!r}")
            continue
        if normalized_quote in normalized_chunk:
            kept_entities.append(candidate)
        else:
            rejections.append(f"quote not in source: {quote!r}")

    for candidate in candidate_relations:
        quote = candidate.exact_quote
        normalized_quote = _normalize(quote)
        if not normalized_quote:
            rejections.append(
                f"empty quote on relation subj={candidate.subj_span!r}"
            )
            continue
        if normalized_quote in normalized_chunk:
            kept_relations.append(candidate)
        else:
            rejections.append(f"quote not in source: {quote!r}")

    return VerifierResult(
        kept_entities=kept_entities,
        kept_relations=kept_relations,
        rejection_reasons=rejections,
    )


__all__ = ["VerifierResult", "verify_candidates"]
```

- [ ] **Step 3: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_extraction_verifier.py -v
.venv/bin/python -m ruff check app/services/extraction tests/test_extraction_verifier.py
.venv/bin/python -m mypy app/services/extraction
git add app/services/extraction/__init__.py app/services/extraction/_verifier.py tests/test_extraction_verifier.py
git commit -m "add deterministic quote verifier for extraction"
```

(Create empty `app/services/extraction/__init__.py` first if needed.)

---

## Task 3: Prompts (`_prompts.py` + config.py)

- [ ] **Step 1: Test**

```python
# tests/test_extraction_prompts.py
def test_build_extraction_messages_includes_reminders_at_start_and_end() -> None:
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(
        chunk_id="11111111-1111-1111-1111-111111111111",
        chunk_text="Apple Inc. announced a new product.",
    )

    assert messages[0]["role"] == "system"
    assert "verbatim" in messages[0]["content"].lower()
    assert messages[-1]["role"] == "user"
    assert "Apple Inc. announced a new product." in messages[-1]["content"]
    assert "verbatim" in messages[-1]["content"].lower()


def test_build_extraction_messages_includes_chunk_id_in_user_message() -> None:
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(
        chunk_id="abc-chunk-id",
        chunk_text="Sample text.",
    )

    assert "abc-chunk-id" in messages[-1]["content"]


def test_extraction_constants_have_documented_defaults() -> None:
    from app.services.extraction import config

    assert config.EXTRACTION_MODEL == "gpt-4o-mini"
    assert config.PROMPT_VERSION == "extraction-v1"
    assert config.MAX_RESPONSE_TOKENS > 0
```

- [ ] **Step 2: Implement `config.py`**

```python
# app/services/extraction/config.py
from typing import Final

EXTRACTION_MODEL: Final[str] = "gpt-4o-mini"
PROMPT_VERSION: Final[str] = "extraction-v1"
MAX_RESPONSE_TOKENS: Final[int] = 4000

__all__ = ["EXTRACTION_MODEL", "MAX_RESPONSE_TOKENS", "PROMPT_VERSION"]
```

- [ ] **Step 3: Implement `_prompts.py`**

```python
# app/services/extraction/_prompts.py
from app.db.models_graph import EntityType, RelationType

_ENTITY_TYPES = ", ".join(t.value for t in EntityType)
_RELATION_TYPES = ", ".join(t.value for t in RelationType)


_SYSTEM_PROMPT = """\
You are a structured-extraction assistant for financial and regulatory documents.
Output a JSON object with two keys: candidate_entities, candidate_relations.
Every entity and every relation MUST include an "exact_quote" field copied
VERBATIM from the source text. Do not paraphrase. Do not invent quotes. If you
cannot find a verbatim quote, omit the candidate.
"""


def build_extraction_messages(*, chunk_id: str, chunk_text: str) -> list[dict[str, str]]:
    user_prompt = f"""\
Source chunk (chunk_id: {chunk_id}):
---
{chunk_text}
---

Extract entities and relations as JSON. Schema:
{{
  "candidate_entities": [
    {{
      "text_span": "<the span as it appears>",
      "suggested_type": "<one of: {_ENTITY_TYPES}>",
      "context_excerpt": "<surrounding text>",
      "exact_quote": "<MUST appear verbatim in source chunk>",
      "extraction_confidence": <0 to 1>
    }}
  ],
  "candidate_relations": [
    {{
      "subj_span": "<subject text>",
      "predicate": "<one of: {_RELATION_TYPES}>",
      "obj_span": "<object text>",
      "exact_quote": "<MUST appear verbatim in source chunk>",
      "is_explicit": <true|false>,
      "extraction_confidence": <0 to 1>
    }}
  ]
}}

Reminder: every exact_quote MUST appear verbatim in the source chunk above.
"""

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


__all__ = ["build_extraction_messages"]
```

- [ ] **Step 4: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_extraction_prompts.py -v
.venv/bin/python -m ruff check app/services/extraction tests/test_extraction_prompts.py
.venv/bin/python -m mypy app/services/extraction
git add app/services/extraction/config.py app/services/extraction/_prompts.py tests/test_extraction_prompts.py
git commit -m "add extraction prompt template and config constants"
```

---

## Task 4: LLM call wrapper (`_llm_call.py`)

Mocks the `LlmClient.complete` API (Phase 1) and the orchestrator `pause`/`fail` (also Phase 1). Need to verify those exact method signatures by reading `app/services/llm.py` and `app/services/run_orchestrator.py` before implementing.

- [ ] **Step 1: Inspect Phase 1 APIs**

```bash
grep -n "def complete" services/api/app/services/llm.py
grep -n "def pause\|def fail" services/api/app/services/run_orchestrator.py
```

Note the exact kwargs each accepts; the test mocks must match.

- [ ] **Step 2: Tests**

```python
# tests/test_extraction_llm_call.py
import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_call_llm_for_extraction_returns_parsed_response(populated_session) -> None:
    from app.services.extraction._llm_call import call_llm_for_extraction

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps({"candidate_entities": [], "candidate_relations": []}),
            model="gpt-4o-mini-2024-07-18",
        )

    response = await call_llm_for_extraction(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_text="hello world",
        evidence_id=uuid.uuid4(),
        llm_complete=fake_complete,
        orchestrator_pause=lambda **kwargs: None,
        orchestrator_fail=lambda **kwargs: None,
    )

    parsed = json.loads(response.content)
    assert parsed["candidate_entities"] == []


async def test_call_llm_routes_budget_paused_to_orchestrator_pause(populated_session) -> None:
    from app.services.extraction._llm_call import ExtractionError, call_llm_for_extraction
    from app.services.llm import BudgetPausedError

    pause_calls: list[dict] = []

    async def fake_complete(**kwargs: Any) -> Any:
        raise BudgetPausedError("budget hard limit")

    async def fake_pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionError):
        await call_llm_for_extraction(
            session=populated_session,
            run_id=run_id,
            chunk_id=uuid.uuid4(),
            chunk_text="hello",
            evidence_id=uuid.uuid4(),
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=lambda **kwargs: None,
        )

    assert len(pause_calls) == 1
    assert pause_calls[0]["run_id"] == run_id


async def test_call_llm_routes_budget_killed_to_orchestrator_fail(populated_session) -> None:
    from app.services.extraction._llm_call import ExtractionError, call_llm_for_extraction
    from app.services.llm import BudgetKilledError

    fail_calls: list[dict] = []

    async def fake_complete(**kwargs: Any) -> Any:
        raise BudgetKilledError("catastrophic")

    async def fake_fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionError):
        await call_llm_for_extraction(
            session=populated_session,
            run_id=run_id,
            chunk_id=uuid.uuid4(),
            chunk_text="hello",
            evidence_id=uuid.uuid4(),
            llm_complete=fake_complete,
            orchestrator_pause=lambda **kwargs: None,
            orchestrator_fail=fake_fail,
        )

    assert fail_calls[0]["run_id"] == run_id
```

- [ ] **Step 3: Implement**

```python
# app/services/extraction/_llm_call.py
"""
LlmClient integration for extraction.

NOTE: LlmClient.complete currently commits the caller-provided session
(see Phase 1 handoff for context). This module passes the session through;
callers should expect the LLM-call's call-log row to be committed even if a
later step in extract_from_chunk fails.
"""
import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extraction._prompts import build_extraction_messages
from app.services.extraction.config import EXTRACTION_MODEL, MAX_RESPONSE_TOKENS
from app.services.llm import BudgetKilledError, BudgetPausedError


class ExtractionError(Exception):
    pass


async def call_llm_for_extraction(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    chunk_id: uuid.UUID,
    chunk_text: str,
    evidence_id: uuid.UUID,
    llm_complete: Callable[..., Awaitable[Any]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
) -> Any:
    messages = build_extraction_messages(chunk_id=str(chunk_id), chunk_text=chunk_text)
    prompt_hash = hashlib.sha256(json.dumps(messages).encode("utf-8")).hexdigest()

    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=EXTRACTION_MODEL,
            messages=messages,
            prompt_hash=prompt_hash,
            evidence_ids=[evidence_id],
            response_format={"type": "json_object"},
            max_tokens=MAX_RESPONSE_TOKENS,
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise ExtractionError("extraction paused by budget guard") from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise ExtractionError("extraction killed by budget guard") from exc

    return response


__all__ = ["ExtractionError", "call_llm_for_extraction"]
```

**Important:** if `LlmClient.complete`'s actual signature differs from what's mocked here (e.g., `evidence_ids` is not a kwarg), align both the implementation AND the test fake to match the real signature. Read `app/services/llm.py` before adjusting.

- [ ] **Step 4: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_extraction_llm_call.py -v
.venv/bin/python -m ruff check app/services/extraction tests/test_extraction_llm_call.py
.venv/bin/python -m mypy app/services/extraction
git add app/services/extraction/_llm_call.py tests/test_extraction_llm_call.py
git commit -m "add extraction llm call wrapper with budget-to-orchestrator routing"
```

---

## Task 5: `core.py` — `extract_from_chunk` orchestrator

Ties prompts + LLM + verifier together. Returns a typed `ExtractionResult`.

- [ ] **Step 1: Tests**

```python
# tests/test_extraction_core.py
import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_extract_from_chunk_happy_path(populated_session) -> None:
    from app.schemas.extraction import EvidenceChunkRef
    from app.services.extraction.core import extract_from_chunk

    chunk_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    chunk_text = "Apple Inc. files annual reports with the SEC."

    chunk = EvidenceChunkRef(
        chunk_id=chunk_id,
        evidence_id=evidence_id,
        chunk_index=0,
        text=chunk_text,
        attributes={},
    )

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps(
                {
                    "candidate_entities": [
                        {
                            "text_span": "Apple Inc.",
                            "suggested_type": "company",
                            "context_excerpt": "Apple Inc. files annual reports",
                            "exact_quote": "Apple Inc.",
                            "extraction_confidence": 0.95,
                        }
                    ],
                    "candidate_relations": [
                        {
                            "subj_span": "Apple Inc.",
                            "predicate": "regulated_by",
                            "obj_span": "SEC",
                            "exact_quote": "Apple Inc. files annual reports with the SEC.",
                            "is_explicit": True,
                            "extraction_confidence": 0.91,
                        }
                    ],
                }
            ),
            model="gpt-4o-mini-2024-07-18",
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=lambda **kwargs: None,
        orchestrator_fail=lambda **kwargs: None,
    )

    assert result.chunk_id == chunk_id
    assert result.verified is True
    assert len(result.candidate_entities) == 1
    assert len(result.candidate_relations) == 1
    assert result.rejection_reasons == []


async def test_extract_from_chunk_rejects_fabricated_quote(populated_session) -> None:
    from app.schemas.extraction import EvidenceChunkRef
    from app.services.extraction.core import extract_from_chunk

    chunk = EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text="Apple Inc. announced a new product line.",
        attributes={},
    )

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps(
                {
                    "candidate_entities": [
                        {
                            "text_span": "Microsoft",
                            "suggested_type": "company",
                            "context_excerpt": "...",
                            "exact_quote": "Microsoft acquired LinkedIn",  # fabricated
                            "extraction_confidence": 0.5,
                        }
                    ],
                    "candidate_relations": [],
                }
            ),
            model="gpt-4o-mini-2024-07-18",
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=lambda **kwargs: None,
        orchestrator_fail=lambda **kwargs: None,
    )

    assert result.verified is False
    assert result.candidate_entities == []
    assert len(result.rejection_reasons) == 1
```

- [ ] **Step 2: Implement**

```python
# app/services/extraction/core.py
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import (
    CandidateEntity,
    CandidateRelation,
    EvidenceChunkRef,
    ExtractionResult,
)
from app.services.extraction._llm_call import ExtractionError, call_llm_for_extraction
from app.services.extraction._verifier import verify_candidates
from app.services.extraction.config import PROMPT_VERSION


async def extract_from_chunk(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    chunk: EvidenceChunkRef,
    llm_complete: Callable[..., Awaitable[Any]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
) -> ExtractionResult:
    response = await call_llm_for_extraction(
        session=session,
        run_id=run_id,
        chunk_id=chunk.chunk_id,
        chunk_text=chunk.text,
        evidence_id=chunk.evidence_id,
        llm_complete=llm_complete,
        orchestrator_pause=orchestrator_pause,
        orchestrator_fail=orchestrator_fail,
    )

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"LLM returned non-JSON content: {exc}") from exc

    raw_entities = payload.get("candidate_entities", [])
    raw_relations = payload.get("candidate_relations", [])

    candidate_entities = [
        CandidateEntity.model_validate({**row, "chunk_id": chunk.chunk_id})
        for row in raw_entities
    ]
    candidate_relations = [
        CandidateRelation.model_validate({**row, "chunk_id": chunk.chunk_id})
        for row in raw_relations
    ]

    verifier_result = verify_candidates(
        chunk_text=chunk.text,
        candidate_entities=candidate_entities,
        candidate_relations=candidate_relations,
    )

    model_id = str(getattr(response, "model", "unknown"))

    return ExtractionResult(
        chunk_id=chunk.chunk_id,
        candidate_entities=verifier_result.kept_entities,
        candidate_relations=verifier_result.kept_relations,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        verified=len(verifier_result.rejection_reasons) == 0,
        rejection_reasons=verifier_result.rejection_reasons,
    )


__all__ = ["extract_from_chunk"]
```

- [ ] **Step 3: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_extraction_core.py -v
.venv/bin/python -m ruff check app/services/extraction tests/test_extraction_core.py
.venv/bin/python -m mypy app/services/extraction
git add app/services/extraction/core.py tests/test_extraction_core.py
git commit -m "add extract_from_chunk orchestrator with verifier integration"
```

---

## Task 6: Public exports

- [ ] Overwrite `app/services/extraction/__init__.py`:

```python
from app.services.extraction._llm_call import ExtractionError
from app.services.extraction.core import extract_from_chunk

__all__ = ["ExtractionError", "extract_from_chunk"]
```

Add a quick exports test (1 test). Commit `expose extraction public api`.

---

## Task 7: Final verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app
```

Expected: ≥290 pass, ruff + mypy clean, no alembic changes.

---

## Done criteria

- 7 task commits on `freddysongg/phase-3d-cited-extraction`.
- `extract_from_chunk` async function as the public entry point.
- Deterministic regex verifier exhaustively tested.
- First `LlmClient` caller — budget errors routed to orchestrator.
- `app/schemas/extraction.py` appended with 3 candidate/result types.
- No changes to `app/config.py`, `app/services/run_orchestrator.py`, or `app/workers/tasks.py`.
- Not pushed.
