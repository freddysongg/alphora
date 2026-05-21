# Phase 3e — Entity Resolution Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 5-step entity resolution pipeline — alias match → external-ID match → fuzzy match → (stubbed) LLM disambiguation → new entity with review.

**Architecture:** New `app/services/entity_resolution/` sub-package. Each step is a single async function. `resolve_candidate()` orchestrator runs steps 1→5 in sequence; each step either resolves or falls through. Adds `rapidfuzz` as a runtime dependency. Appends `EntityResolutionOutcome` to `app/schemas/extraction.py`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Pydantic v2, **`rapidfuzz>=3.0` (NEW)**. No new clients, no new migrations.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3e-entity-resolution-design.md`
**Coordination:** `docs/superpowers/phase-3-parallel-coordination.md`

**Working dir:** `services/api/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Modified — add `rapidfuzz>=3.0` to `dependencies` |
| `app/schemas/extraction.py` | Append `EntityResolutionOutcome` |
| `app/services/entity_resolution/__init__.py` | Public `resolve_candidate`, `ResolutionError`, `LlmDisambiguator` |
| `app/services/entity_resolution/_normalize.py` | `normalize_for_match` (lowercase + strip suffixes) |
| `app/services/entity_resolution/_alias_match.py` | `step_1_alias_match` |
| `app/services/entity_resolution/_external_id_match.py` | `step_2_external_id_match` + regex patterns |
| `app/services/entity_resolution/_fuzzy_match.py` | `step_3_fuzzy_match` |
| `app/services/entity_resolution/_llm_disambig.py` | `step_4_llm_disambiguation` (stub) |
| `app/services/entity_resolution/_create_new.py` | `step_5_create_new_entity_with_review` |
| `app/services/entity_resolution/pipeline.py` | `resolve_candidate` |

---

## Task 1: Append `EntityResolutionOutcome` to `app/schemas/extraction.py`

Wait for 3b to create the file.

- [ ] Tests at `tests/test_extraction_schemas_resolution.py`:

```python
import uuid

def test_entity_resolution_outcome_is_frozen() -> None:
    from app.db.models_graph import EntityResolutionDecisionKind
    from app.schemas.extraction import EntityResolutionOutcome

    outcome = EntityResolutionOutcome(
        candidate_text="Apple",
        decision_kind=EntityResolutionDecisionKind.alias_match,
        chosen_entity_id=uuid.uuid4(),
        review_id=None,
        confidence=0.95,
    )
    assert outcome.confidence == 0.95


def test_entity_resolution_outcome_in_all() -> None:
    from app.schemas import extraction

    assert "EntityResolutionOutcome" in extraction.__all__
```

- [ ] Append to `app/schemas/extraction.py`:

```python
class EntityResolutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_text: str
    decision_kind: EntityResolutionDecisionKindEnum
    chosen_entity_id: uuid.UUID | None
    review_id: uuid.UUID | None
    confidence: float
```

Ensure import `EntityResolutionDecisionKindEnum` at top of `extraction.py`. Add the name to `__all__`.

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_extraction_schemas_resolution.py -v
.venv/bin/python -m ruff check app/schemas/extraction.py
.venv/bin/python -m mypy app/schemas/extraction.py
git add app/schemas/extraction.py tests/test_extraction_schemas_resolution.py
git commit -m "add entity resolution outcome contract"
```

---

## Task 2: Add `rapidfuzz` dependency

- [ ] Edit `services/api/pyproject.toml`. Find the `[project] dependencies = [...]` block and add `"rapidfuzz>=3.0",` (alphabetically — between `pydantic-settings` and `redis`).

- [ ] Install:

```bash
cd services/api
.venv/bin/python -m pip install -e .[dev]
```

(Or `uv` equivalent if the repo uses uv.)

- [ ] Verify importable:

```bash
.venv/bin/python -c "import rapidfuzz; print(rapidfuzz.__version__)"
```

- [ ] Commit:

```bash
git add pyproject.toml
git commit -m "add rapidfuzz runtime dependency for entity fuzzy matching"
```

---

## Task 3: `_normalize.py` — name normalization for matching

- [ ] Test `tests/test_entity_resolution_normalize.py`:

```python
def test_normalize_for_match_lowercases() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("Apple Inc.") == "apple"


def test_normalize_for_match_strips_suffixes() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    for raw in ["Microsoft Corp.", "Microsoft Corp", "Microsoft Corporation"]:
        assert normalize_for_match(raw) == "microsoft"


def test_normalize_for_match_collapses_whitespace() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("  Apple   Inc.  ") == "apple"


def test_normalize_for_match_empty_string() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("") == ""
```

- [ ] Implement `app/services/entity_resolution/_normalize.py`:

```python
import re

_SUFFIX_PATTERN = re.compile(
    r"\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|LLC|N\.V\.|S\.A\.|PLC)$",
    flags=re.IGNORECASE,
)


def normalize_for_match(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", name).strip()
    stripped = _SUFFIX_PATTERN.sub("", collapsed).strip()
    return stripped.lower()


__all__ = ["normalize_for_match"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_normalize.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_normalize.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/__init__.py app/services/entity_resolution/_normalize.py tests/test_entity_resolution_normalize.py
git commit -m "add entity resolution name normalization"
```

(Create empty `__init__.py` first.)

---

## Task 4: Step 1 — alias match (`_alias_match.py`)

- [ ] Test `tests/test_entity_resolution_alias_match.py`:

```python
import uuid

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(session, *, type, canonical_name, aliases, external_ids=None):
    from app.db.models_graph import Entity

    entity = Entity(
        type=type.value,
        canonical_name=canonical_name,
        aliases=aliases,
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


async def test_alias_match_returns_unique_hit(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple", "Apple Inc."],
        )

    async with populated_session.begin():
        match = await step_1_alias_match(
            session=populated_session, candidate_text="Apple"
        )

    assert match is not None
    assert match.canonical_name == "Apple Inc."


async def test_alias_match_returns_none_on_zero_matches(populated_session) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        match = await step_1_alias_match(
            session=populated_session, candidate_text="Unknown"
        )

    assert match is None


async def test_alias_match_returns_none_on_ambiguous_hits(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Hospitality REIT",
            aliases=["Apple"],
        )

    async with populated_session.begin():
        match = await step_1_alias_match(
            session=populated_session, candidate_text="Apple"
        )

    assert match is None


async def test_alias_match_skips_merged_tombstones(populated_session) -> None:
    from app.db.models_graph import Entity, EntityType
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        tombstone = await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Computer, Inc.",
            aliases=["Apple"],
        )
        tombstone.merged_into_id = survivor.id

    async with populated_session.begin():
        match = await step_1_alias_match(
            session=populated_session, candidate_text="Apple"
        )

    assert match is not None
    assert match.id == survivor.id
```

- [ ] Implement `_alias_match.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity


async def step_1_alias_match(
    *, session: AsyncSession, candidate_text: str,
) -> Entity | None:
    """Return the unique entity whose aliases contain candidate_text exactly.
    Excludes merged tombstones.
    """
    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    candidates = [
        entity
        for entity in result.scalars().all()
        if isinstance(entity.aliases, list) and candidate_text in entity.aliases
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


__all__ = ["step_1_alias_match"]
```

The fetch-all-and-filter approach is acceptable at v0 scale; future indexing optimization documented.

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_alias_match.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_alias_match.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/_alias_match.py tests/test_entity_resolution_alias_match.py
git commit -m "add entity resolution step 1 alias match"
```

---

## Task 5: Step 2 — external-ID match (`_external_id_match.py`)

- [ ] Tests `tests/test_entity_resolution_external_id_match.py`:

```python
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(session, *, type, canonical_name, external_ids, aliases=None):
    from app.db.models_graph import Entity

    entity = Entity(
        type=type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids=external_ids,
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


async def test_external_id_match_finds_ticker_with_nasdaq_context(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._external_id_match import step_2_external_id_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL", "cik": "0000320193"},
        )

    async with populated_session.begin():
        match = await step_2_external_id_match(
            session=populated_session,
            context_excerpt="Apple Inc. (Nasdaq: AAPL) reported earnings...",
        )

    assert match is not None
    assert match.canonical_name == "Apple Inc."


async def test_external_id_match_finds_cik(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._external_id_match import step_2_external_id_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            external_ids={"cik": "0000320193"},
        )

    async with populated_session.begin():
        match = await step_2_external_id_match(
            session=populated_session,
            context_excerpt="See filing CIK 0000320193 for details.",
        )

    assert match is not None


async def test_external_id_match_rejects_ticker_without_context_marker(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._external_id_match import step_2_external_id_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )

    async with populated_session.begin():
        # No "$AAPL" / "Nasdaq:" / "NYSE:" context — should NOT match
        match = await step_2_external_id_match(
            session=populated_session,
            context_excerpt="The bag is APPLEy in color.",
        )

    assert match is None


async def test_external_id_match_returns_none_when_ambiguous(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._external_id_match import step_2_external_id_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Hospitality REIT",
            external_ids={"ticker": "APLE"},
        )

    async with populated_session.begin():
        match = await step_2_external_id_match(
            session=populated_session,
            context_excerpt="Tickers AAPL and APLE traded heavily today.",
        )

    # Two different tickers in context, both match — too ambiguous
    assert match is None
```

- [ ] Implement `_external_id_match.py`:

```python
import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity

_CIK_PATTERN = re.compile(r"\bCIK\s+(\d{1,10})\b", re.IGNORECASE)
_TICKER_PATTERN = re.compile(
    r"(?:\$|Nasdaq:\s*|NYSE:\s*|NYSEMKT:\s*|AMEX:\s*)([A-Z]{1,5})\b"
)
_LEI_PATTERN = re.compile(r"\b([A-Z0-9]{20})\b")


def _extract_external_id_candidates(text: str) -> list[tuple[str, str]]:
    """Return list of (id_key, id_value) tuples extracted from text."""
    out: list[tuple[str, str]] = []
    for match in _CIK_PATTERN.finditer(text):
        out.append(("cik", match.group(1).zfill(10)))
    for match in _TICKER_PATTERN.finditer(text):
        out.append(("ticker", match.group(1)))
    for match in _LEI_PATTERN.finditer(text):
        # LEI is exactly 20 alphanumeric; suppress if it's clearly a CIK (digits only padded)
        if not match.group(1).isdigit():
            out.append(("lei", match.group(1)))
    return out


async def step_2_external_id_match(
    *, session: AsyncSession, context_excerpt: str,
) -> Entity | None:
    """Look up entities by external IDs found in context.
    Returns the unique match if exactly one (id_key, id_value) hits exactly one entity.
    """
    candidates = _extract_external_id_candidates(context_excerpt)
    if not candidates:
        return None

    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    entities = result.scalars().all()

    matched: set[Entity] = set()
    for id_key, id_value in candidates:
        for entity in entities:
            if not isinstance(entity.external_ids, dict):
                continue
            if entity.external_ids.get(id_key) == id_value:
                matched.add(entity)

    if len(matched) == 1:
        return next(iter(matched))
    return None


__all__ = ["step_2_external_id_match"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_external_id_match.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_external_id_match.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/_external_id_match.py tests/test_entity_resolution_external_id_match.py
git commit -m "add entity resolution step 2 external id match"
```

---

## Task 6: Step 3 — fuzzy match (`_fuzzy_match.py`)

- [ ] Tests cover: single high-confidence match resolves; two-close-matches returns None (fall-through); below threshold returns None; suffix stripping (`"Apple Inc."` matches existing `"Apple"`).

```python
# tests/test_entity_resolution_fuzzy_match.py
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(session, *, type, canonical_name, aliases=None):
    from app.db.models_graph import Entity

    entity = Entity(
        type=type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids={},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


async def test_fuzzy_match_returns_unique_high_score(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple Inc.", "Apple"],
        )
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Microsoft Corp.",
            aliases=["Microsoft"],
        )

    async with populated_session.begin():
        match, score = await step_3_fuzzy_match(
            session=populated_session, candidate_text="Apple Inc"
        )

    assert match is not None
    assert match.canonical_name == "Apple Inc."
    assert score >= 0.85


async def test_fuzzy_match_falls_through_below_threshold(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )

    async with populated_session.begin():
        match, _ = await step_3_fuzzy_match(
            session=populated_session, candidate_text="Tesla"
        )

    assert match is None


async def test_fuzzy_match_falls_through_on_two_close_matches(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Hospitality",
            aliases=["Apple Hospitality"],
        )

    async with populated_session.begin():
        match, _ = await step_3_fuzzy_match(
            session=populated_session, candidate_text="Apple"
        )

    # Both score ≥0.85 → ambiguous
    assert match is None
```

- [ ] Implement `_fuzzy_match.py`:

```python
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity
from app.services.entity_resolution._normalize import normalize_for_match

_FUZZY_THRESHOLD: float = 0.85
_AMBIGUITY_MARGIN: float = 0.80


def _score(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b) / 100.0


async def step_3_fuzzy_match(
    *, session: AsyncSession, candidate_text: str,
) -> tuple[Entity | None, float]:
    """Return the single best fuzzy match, or (None, 0.0) if ambiguous / below threshold."""
    normalized_candidate = normalize_for_match(candidate_text)
    if not normalized_candidate:
        return None, 0.0

    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    entities = result.scalars().all()

    scored: list[tuple[Entity, float]] = []
    for entity in entities:
        names: list[str] = [entity.canonical_name] + list(entity.aliases or [])
        best = max(_score(normalized_candidate, normalize_for_match(name)) for name in names)
        scored.append((entity, best))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    if not scored:
        return None, 0.0

    top_entity, top_score = scored[0]
    if top_score < _FUZZY_THRESHOLD:
        return None, top_score

    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if second_score >= _AMBIGUITY_MARGIN:
        return None, top_score

    return top_entity, top_score


__all__ = ["step_3_fuzzy_match"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_fuzzy_match.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_fuzzy_match.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/_fuzzy_match.py tests/test_entity_resolution_fuzzy_match.py
git commit -m "add entity resolution step 3 fuzzy match"
```

---

## Task 7: Step 4 — LLM disambiguation stub (`_llm_disambig.py`)

- [ ] Test `tests/test_entity_resolution_llm_disambig.py`:

```python
import uuid

import pytest


async def test_llm_disambig_stub_returns_none() -> None:
    from app.services.entity_resolution._llm_disambig import step_4_llm_disambiguation

    result = await step_4_llm_disambiguation(
        candidate=_fake_candidate(),
        candidate_entities=[],
        disambiguator=None,
    )

    assert result is None


async def test_llm_disambig_uses_injected_callable() -> None:
    from app.services.entity_resolution._llm_disambig import step_4_llm_disambiguation

    chosen = uuid.uuid4()

    async def fake(candidate, candidates):
        return chosen

    result = await step_4_llm_disambiguation(
        candidate=_fake_candidate(),
        candidate_entities=[],
        disambiguator=fake,
    )

    assert result == chosen


def _fake_candidate():
    from app.db.models_graph import EntityType
    from app.schemas.extraction import CandidateEntity

    return CandidateEntity(
        text_span="Apple",
        suggested_type=EntityType.company,
        context_excerpt="...",
        exact_quote="Apple",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )
```

- [ ] Implement `_llm_disambig.py`:

```python
import uuid
from collections.abc import Awaitable, Callable

from app.db.models_graph import Entity
from app.schemas.extraction import CandidateEntity

LlmDisambiguator = Callable[
    [CandidateEntity, list[Entity]],
    Awaitable[uuid.UUID | None],
]


async def step_4_llm_disambiguation(
    *,
    candidate: CandidateEntity,
    candidate_entities: list[Entity],
    disambiguator: LlmDisambiguator | None,
) -> uuid.UUID | None:
    if disambiguator is None:
        return None
    return await disambiguator(candidate, candidate_entities)


__all__ = ["LlmDisambiguator", "step_4_llm_disambiguation"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_llm_disambig.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_llm_disambig.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/_llm_disambig.py tests/test_entity_resolution_llm_disambig.py
git commit -m "add entity resolution step 4 llm disambiguation stub"
```

---

## Task 8: Step 5 — create new entity + review row (`_create_new.py`)

- [ ] Tests cover: new entity persisted with correct fields; review row persisted; outcome carries both IDs.

```python
# tests/test_entity_resolution_create_new.py
import uuid

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_step_5_creates_entity_and_review(populated_session) -> None:
    from app.db.models_graph import (
        EntityResolutionReviewStatus,
        EntityType,
        EntityResolutionDecisionKind,
    )
    from app.schemas.extraction import CandidateEntity
    from app.services.entity_resolution._create_new import (
        step_5_create_new_entity_with_review,
    )

    candidate = CandidateEntity(
        text_span="Foobar Inc.",
        suggested_type=EntityType.company,
        context_excerpt="Foobar Inc. announced a partnership.",
        exact_quote="Foobar Inc.",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.6,
    )

    async with populated_session.begin():
        outcome = await step_5_create_new_entity_with_review(
            session=populated_session,
            candidate=candidate,
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.new_entity.value or \
           outcome.decision_kind.value == "new_entity"  # noqa
    assert outcome.chosen_entity_id is not None
    assert outcome.review_id is not None
    assert outcome.confidence == 0.6
```

- [ ] Implement `_create_new.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityResolutionDecisionKind,
    EntityResolutionReview,
    EntityResolutionReviewStatus,
)
from app.schemas.extraction import CandidateEntity, EntityResolutionOutcome


async def step_5_create_new_entity_with_review(
    *, session: AsyncSession, candidate: CandidateEntity,
) -> EntityResolutionOutcome:
    new_entity = Entity(
        type=candidate.suggested_type.value,
        canonical_name=candidate.text_span,
        aliases=[candidate.text_span],
        external_ids={},
        attributes={"created_by": "entity_resolution_v1"},
        confidence=candidate.extraction_confidence,
        needs_review=True,
    )
    session.add(new_entity)
    await session.flush()

    review = EntityResolutionReview(
        candidate_text=candidate.text_span,
        suggested_type=candidate.suggested_type.value,
        context_excerpt=candidate.context_excerpt,
        decision_kind=EntityResolutionDecisionKind.new_entity.value,
        candidate_entity_ids=[],
        chosen_entity_id=new_entity.id,
        status=EntityResolutionReviewStatus.pending.value,
        confidence=candidate.extraction_confidence,
        evidence_id=None,
        notes=None,
    )
    session.add(review)
    await session.flush()

    return EntityResolutionOutcome(
        candidate_text=candidate.text_span,
        decision_kind=EntityResolutionDecisionKind.new_entity,
        chosen_entity_id=new_entity.id,
        review_id=review.id,
        confidence=candidate.extraction_confidence,
    )


__all__ = ["step_5_create_new_entity_with_review"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_create_new.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_create_new.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/_create_new.py tests/test_entity_resolution_create_new.py
git commit -m "add entity resolution step 5 new entity with review"
```

---

## Task 9: Pipeline orchestrator (`pipeline.py`)

- [ ] End-to-end tests covering each step's hit path.

```python
# tests/test_entity_resolution_pipeline.py
import uuid

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed(session, *, type, name, aliases=None, external_ids=None):
    from app.db.models_graph import Entity

    entity = Entity(
        type=type.value,
        canonical_name=name,
        aliases=aliases or [],
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


def _candidate(text_span, context):
    from app.db.models_graph import EntityType
    from app.schemas.extraction import CandidateEntity

    return CandidateEntity(
        text_span=text_span,
        suggested_type=EntityType.company,
        context_excerpt=context,
        exact_quote=text_span,
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


async def test_pipeline_resolves_via_alias_when_exact_unique(populated_session) -> None:
    from app.db.models_graph import EntityResolutionDecisionKind, EntityType
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        seeded = await _seed(
            populated_session,
            type=EntityType.company,
            name="Apple Inc.",
            aliases=["Apple"],
        )

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session, candidate=_candidate("Apple", "Apple released a product.")
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.alias_match
    assert outcome.chosen_entity_id == seeded.id


async def test_pipeline_creates_new_entity_when_no_match(populated_session) -> None:
    from app.db.models_graph import EntityResolutionDecisionKind
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("UnseenEntity", "context"),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.new_entity
    assert outcome.review_id is not None
```

- [ ] Implement `pipeline.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityResolutionDecisionKind
from app.schemas.extraction import CandidateEntity, EntityResolutionOutcome
from app.services.entity_resolution._alias_match import step_1_alias_match
from app.services.entity_resolution._create_new import step_5_create_new_entity_with_review
from app.services.entity_resolution._external_id_match import step_2_external_id_match
from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match
from app.services.entity_resolution._llm_disambig import (
    LlmDisambiguator,
    step_4_llm_disambiguation,
)


class ResolutionError(Exception):
    pass


async def resolve_candidate(
    *,
    session: AsyncSession,
    candidate: CandidateEntity,
    llm_disambiguator: LlmDisambiguator | None = None,
) -> EntityResolutionOutcome:
    alias_hit = await step_1_alias_match(
        session=session, candidate_text=candidate.text_span
    )
    if alias_hit is not None:
        return EntityResolutionOutcome(
            candidate_text=candidate.text_span,
            decision_kind=EntityResolutionDecisionKind.alias_match,
            chosen_entity_id=alias_hit.id,
            review_id=None,
            confidence=0.95,
        )

    ext_id_hit = await step_2_external_id_match(
        session=session, context_excerpt=candidate.context_excerpt
    )
    if ext_id_hit is not None:
        return EntityResolutionOutcome(
            candidate_text=candidate.text_span,
            decision_kind=EntityResolutionDecisionKind.external_id_match,
            chosen_entity_id=ext_id_hit.id,
            review_id=None,
            confidence=0.99,
        )

    fuzzy_hit, fuzzy_score = await step_3_fuzzy_match(
        session=session, candidate_text=candidate.text_span
    )
    if fuzzy_hit is not None:
        return EntityResolutionOutcome(
            candidate_text=candidate.text_span,
            decision_kind=EntityResolutionDecisionKind.fuzzy_match,
            chosen_entity_id=fuzzy_hit.id,
            review_id=None,
            confidence=fuzzy_score,
        )

    disambiguated_id = await step_4_llm_disambiguation(
        candidate=candidate,
        candidate_entities=[],
        disambiguator=llm_disambiguator,
    )
    if disambiguated_id is not None:
        return EntityResolutionOutcome(
            candidate_text=candidate.text_span,
            decision_kind=EntityResolutionDecisionKind.llm_disambiguation,
            chosen_entity_id=disambiguated_id,
            review_id=None,
            confidence=0.75,
        )

    return await step_5_create_new_entity_with_review(
        session=session, candidate=candidate
    )


__all__ = ["ResolutionError", "resolve_candidate"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_resolution_pipeline.py -v
.venv/bin/python -m ruff check app/services/entity_resolution tests/test_entity_resolution_pipeline.py
.venv/bin/python -m mypy app/services/entity_resolution
git add app/services/entity_resolution/pipeline.py tests/test_entity_resolution_pipeline.py
git commit -m "add entity resolution 5-step pipeline orchestrator"
```

---

## Task 10: Public exports

- [ ] Overwrite `app/services/entity_resolution/__init__.py`:

```python
from app.services.entity_resolution._llm_disambig import LlmDisambiguator
from app.services.entity_resolution.pipeline import ResolutionError, resolve_candidate

__all__ = ["LlmDisambiguator", "ResolutionError", "resolve_candidate"]
```

Add an exports test. Commit `expose entity resolution public api`.

---

## Task 11: Final verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app
```

Expected: ≥290 pass. ruff + mypy clean. No alembic changes.

---

## Done criteria

- 11 task commits on `freddysongg/phase-3e-entity-resolution`.
- `resolve_candidate` async function as the public entry point.
- 5 step functions, each independently testable.
- `rapidfuzz` added to `pyproject.toml`.
- `EntityResolutionOutcome` appended to `app/schemas/extraction.py`.
- LLM disambiguation stubbed (real callable plugs in via injected `llm_disambiguator`).
- No new migrations. No changes to other phase scopes.
- Not pushed.
