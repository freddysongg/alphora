import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityResolutionDecisionKind,
    EntityType,
)
from app.schemas.common import EntityTypeEnum


class _StubCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    text_span: str
    suggested_type: EntityTypeEnum
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


@pytest_asyncio.fixture()
async def populated_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed(
    session: AsyncSession,
    *,
    canonical_name: str,
    aliases: list[str] | None = None,
    external_ids: dict[str, str] | None = None,
    entity_type: EntityType = EntityType.company,
) -> Entity:
    entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


def _candidate(text_span: str, context: str) -> _StubCandidate:
    return _StubCandidate(
        text_span=text_span,
        suggested_type=EntityTypeEnum.company,
        context_excerpt=context,
        exact_quote=text_span,
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


@pytest.mark.asyncio
async def test_pipeline_resolves_via_alias_when_exact_unique(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        seeded = await _seed(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        seeded_id = seeded.id

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("Apple", "Apple released a product."),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.alias_match
    assert outcome.chosen_entity_id == seeded_id
    assert outcome.review_id is None
    assert outcome.confidence == 0.95


@pytest.mark.asyncio
async def test_pipeline_resolves_via_external_id_when_alias_misses(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        seeded = await _seed(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"ticker": "AAPL"},
        )
        seeded_id = seeded.id

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate(
                "AppleCo",
                "AppleCo (Nasdaq: AAPL) reported earnings.",
            ),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.external_id_match
    assert outcome.chosen_entity_id == seeded_id
    assert outcome.review_id is None
    assert outcome.confidence == 0.99


@pytest.mark.asyncio
async def test_pipeline_resolves_via_fuzzy_when_alias_and_ext_id_miss(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        seeded = await _seed(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple Inc."],
        )
        seeded_id = seeded.id

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("Apple Inc", "Apple Inc filed a report."),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.fuzzy_match
    assert outcome.chosen_entity_id == seeded_id
    assert outcome.review_id is None
    assert outcome.confidence >= 0.85


@pytest.mark.asyncio
async def test_pipeline_resolves_via_llm_when_disambiguator_returns_id(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    chosen = uuid.uuid4()

    async def force_choice(
        _candidate: object, _candidates: list[Entity]
    ) -> uuid.UUID | None:
        return chosen

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("Mystery Co", "Mystery Co did something."),
            llm_disambiguator=force_choice,
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.llm_disambiguation
    assert outcome.chosen_entity_id == chosen
    assert outcome.review_id is None


@pytest.mark.asyncio
async def test_pipeline_forwards_ambiguous_fuzzy_candidates_to_disambiguator(
    populated_session: AsyncSession,
) -> None:
    """When fuzzy match is ambiguous, the LLM disambiguator must receive the top-N entities."""
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        apple_inc = await _seed(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple Inc."],
        )
        apple_hosp = await _seed(
            populated_session,
            canonical_name="Apple Hospitality",
            aliases=["Apple Hospitality"],
        )
        apple_inc_id = apple_inc.id
        apple_hosp_id = apple_hosp.id

    received_candidates: list[Entity] = []

    async def pick_first(
        _candidate: object, candidates: list[Entity]
    ) -> uuid.UUID | None:
        received_candidates.extend(candidates)
        if not candidates:
            return None
        return candidates[0].id

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("Apple", "Apple announced X."),
            llm_disambiguator=pick_first,
        )

    received_ids = {entity.id for entity in received_candidates}
    assert apple_inc_id in received_ids
    assert apple_hosp_id in received_ids
    assert outcome.decision_kind == EntityResolutionDecisionKind.llm_disambiguation
    assert outcome.chosen_entity_id in received_ids


@pytest.mark.asyncio
async def test_pipeline_creates_new_entity_when_no_match(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("UnseenEntity", "context"),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.new_entity
    assert outcome.chosen_entity_id is not None
    assert outcome.review_id is not None


@pytest.mark.asyncio
async def test_pipeline_uses_default_stub_when_no_disambiguator_supplied(
    populated_session: AsyncSession,
) -> None:
    """Stub disambiguator must return None — falls through to step 5."""
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate("NovelCompany", "NovelCompany announced X."),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.new_entity


@pytest.mark.asyncio
async def test_pipeline_alias_takes_precedence_over_external_id(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution.pipeline import resolve_candidate

    async with populated_session.begin():
        alias_winner = await _seed(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        alias_winner_id = alias_winner.id
        await _seed(
            populated_session,
            canonical_name="Other Apple",
            external_ids={"ticker": "AAPL"},
        )

    async with populated_session.begin():
        outcome = await resolve_candidate(
            session=populated_session,
            candidate=_candidate(
                "Apple", "Apple (Nasdaq: AAPL) released a product."
            ),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.alias_match
    assert outcome.chosen_entity_id == alias_winner_id
