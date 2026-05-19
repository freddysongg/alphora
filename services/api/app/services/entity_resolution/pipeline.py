from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityResolutionDecisionKind
from app.schemas.extraction import EntityResolutionOutcome
from app.services.entity_resolution._alias_match import step_1_alias_match
from app.services.entity_resolution._create_new import (
    step_5_create_new_entity_with_review,
)
from app.services.entity_resolution._external_id_match import (
    step_2_external_id_match,
)
from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match
from app.services.entity_resolution._llm_disambig import (
    LlmDisambiguator,
    step_4_llm_disambiguation,
)
from app.services.entity_resolution._types import CandidateLike

_LLM_DECISION_CONFIDENCE: float = 0.75
_ALIAS_DECISION_CONFIDENCE: float = 0.95
_EXTERNAL_ID_DECISION_CONFIDENCE: float = 0.99


class ResolutionError(Exception):
    pass


async def resolve_candidate(
    *,
    session: AsyncSession,
    candidate: CandidateLike,
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
            confidence=_ALIAS_DECISION_CONFIDENCE,
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
            confidence=_EXTERNAL_ID_DECISION_CONFIDENCE,
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
            confidence=_LLM_DECISION_CONFIDENCE,
        )

    return await step_5_create_new_entity_with_review(
        session=session, candidate=candidate
    )


__all__ = ["ResolutionError", "resolve_candidate"]
