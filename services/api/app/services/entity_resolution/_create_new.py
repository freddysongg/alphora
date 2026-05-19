from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityResolutionDecisionKind,
    EntityResolutionReview,
    EntityResolutionReviewStatus,
)
from app.schemas.extraction import EntityResolutionOutcome
from app.services.entity_resolution._types import CandidateLike


async def step_5_create_new_entity_with_review(
    *,
    session: AsyncSession,
    candidate: CandidateLike,
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
