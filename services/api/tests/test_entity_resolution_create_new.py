import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityResolutionDecisionKind,
    EntityResolutionReview,
    EntityResolutionReviewStatus,
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


def _stub_candidate(
    *,
    text_span: str = "Foobar Inc.",
    suggested_type: EntityTypeEnum = EntityTypeEnum.company,
    context_excerpt: str = "Foobar Inc. announced a partnership.",
    extraction_confidence: float = 0.6,
) -> _StubCandidate:
    return _StubCandidate(
        text_span=text_span,
        suggested_type=suggested_type,
        context_excerpt=context_excerpt,
        exact_quote=text_span,
        chunk_id=uuid.uuid4(),
        extraction_confidence=extraction_confidence,
    )


@pytest.mark.asyncio
async def test_step_5_returns_new_entity_decision(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._create_new import (
        step_5_create_new_entity_with_review,
    )

    async with populated_session.begin():
        outcome = await step_5_create_new_entity_with_review(
            session=populated_session,
            candidate=_stub_candidate(),
        )

    assert outcome.decision_kind == EntityResolutionDecisionKind.new_entity
    assert outcome.chosen_entity_id is not None
    assert outcome.review_id is not None
    assert outcome.confidence == 0.6
    assert outcome.candidate_text == "Foobar Inc."


@pytest.mark.asyncio
async def test_step_5_persists_entity_row(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._create_new import (
        step_5_create_new_entity_with_review,
    )

    async with populated_session.begin():
        outcome = await step_5_create_new_entity_with_review(
            session=populated_session,
            candidate=_stub_candidate(),
        )

    assert outcome.chosen_entity_id is not None
    result = await populated_session.execute(
        select(Entity).where(Entity.id == outcome.chosen_entity_id)
    )
    entity = result.scalar_one()

    assert entity.canonical_name == "Foobar Inc."
    assert entity.type == EntityType.company.value
    assert entity.aliases == ["Foobar Inc."]
    assert entity.external_ids == {}
    assert entity.needs_review is True
    assert entity.confidence == 0.6


@pytest.mark.asyncio
async def test_step_5_persists_review_row(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._create_new import (
        step_5_create_new_entity_with_review,
    )

    async with populated_session.begin():
        outcome = await step_5_create_new_entity_with_review(
            session=populated_session,
            candidate=_stub_candidate(),
        )

    assert outcome.review_id is not None
    result = await populated_session.execute(
        select(EntityResolutionReview).where(
            EntityResolutionReview.id == outcome.review_id
        )
    )
    review = result.scalar_one()

    assert review.candidate_text == "Foobar Inc."
    assert review.suggested_type == EntityType.company.value
    assert review.context_excerpt == "Foobar Inc. announced a partnership."
    assert review.decision_kind == EntityResolutionDecisionKind.new_entity.value
    assert review.candidate_entity_ids == []
    assert review.chosen_entity_id == outcome.chosen_entity_id
    assert review.status == EntityResolutionReviewStatus.pending.value
    assert review.confidence == 0.6


@pytest.mark.asyncio
async def test_step_5_preserves_suggested_type(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._create_new import (
        step_5_create_new_entity_with_review,
    )

    async with populated_session.begin():
        outcome = await step_5_create_new_entity_with_review(
            session=populated_session,
            candidate=_stub_candidate(
                text_span="Jane Doe",
                suggested_type=EntityTypeEnum.person,
                context_excerpt="Jane Doe testified.",
                extraction_confidence=0.8,
            ),
        )

    assert outcome.chosen_entity_id is not None
    result = await populated_session.execute(
        select(Entity).where(Entity.id == outcome.chosen_entity_id)
    )
    entity = result.scalar_one()

    assert entity.type == EntityType.person.value
    assert outcome.confidence == 0.8
