import uuid

import pytest
from pydantic import BaseModel, ConfigDict

from app.db.models_graph import Entity, EntityType
from app.services.entity_resolution._types import CandidateLike


class _StubCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    text_span: str
    suggested_type: EntityType
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


def _stub_candidate() -> _StubCandidate:
    return _StubCandidate(
        text_span="Apple",
        suggested_type=EntityType.company,
        context_excerpt="...",
        exact_quote="Apple",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


@pytest.mark.asyncio
async def test_llm_disambig_returns_none_when_disambiguator_omitted() -> None:
    from app.services.entity_resolution._llm_disambig import (
        step_4_llm_disambiguation,
    )

    result = await step_4_llm_disambiguation(
        candidate=_stub_candidate(),
        candidate_entities=[],
        disambiguator=None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_llm_disambig_invokes_injected_callable() -> None:
    from app.services.entity_resolution._llm_disambig import (
        step_4_llm_disambiguation,
    )

    chosen = uuid.uuid4()

    async def fake_disambiguator(
        _candidate: CandidateLike, _candidates: list[Entity]
    ) -> uuid.UUID | None:
        return chosen

    result = await step_4_llm_disambiguation(
        candidate=_stub_candidate(),
        candidate_entities=[],
        disambiguator=fake_disambiguator,
    )

    assert result == chosen


@pytest.mark.asyncio
async def test_llm_disambig_passes_arguments_to_callable() -> None:
    from app.services.entity_resolution._llm_disambig import (
        step_4_llm_disambiguation,
    )

    captured: dict[str, object] = {}

    async def capture(
        candidate: CandidateLike, candidates: list[Entity]
    ) -> uuid.UUID | None:
        captured["candidate"] = candidate
        captured["candidates"] = candidates
        return None

    candidate = _stub_candidate()
    candidate_entities: list[Entity] = []
    await step_4_llm_disambiguation(
        candidate=candidate,
        candidate_entities=candidate_entities,
        disambiguator=capture,
    )

    assert captured["candidate"] is candidate
    assert captured["candidates"] is candidate_entities


@pytest.mark.asyncio
async def test_llm_disambig_disambiguator_returning_none_propagates() -> None:
    from app.services.entity_resolution._llm_disambig import (
        step_4_llm_disambiguation,
    )

    async def fake_disambiguator(
        _candidate: CandidateLike, _candidates: list[Entity]
    ) -> uuid.UUID | None:
        return None

    result = await step_4_llm_disambiguation(
        candidate=_stub_candidate(),
        candidate_entities=[],
        disambiguator=fake_disambiguator,
    )

    assert result is None
