import uuid

import pytest
from pydantic import ValidationError


def test_entity_resolution_outcome_constructs_with_all_fields() -> None:
    from app.db.models_graph import EntityResolutionDecisionKind
    from app.schemas.extraction import EntityResolutionOutcome

    entity_id = uuid.uuid4()
    outcome = EntityResolutionOutcome(
        candidate_text="Apple",
        decision_kind=EntityResolutionDecisionKind.alias_match,
        chosen_entity_id=entity_id,
        review_id=None,
        confidence=0.95,
    )

    assert outcome.candidate_text == "Apple"
    assert outcome.decision_kind == EntityResolutionDecisionKind.alias_match
    assert outcome.chosen_entity_id == entity_id
    assert outcome.review_id is None
    assert outcome.confidence == 0.95


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

    with pytest.raises(ValidationError):
        outcome.confidence = 0.5  # type: ignore[misc]


def test_entity_resolution_outcome_allows_review_id_without_entity() -> None:
    from app.db.models_graph import EntityResolutionDecisionKind
    from app.schemas.extraction import EntityResolutionOutcome

    review_id = uuid.uuid4()
    outcome = EntityResolutionOutcome(
        candidate_text="Mystery Corp",
        decision_kind=EntityResolutionDecisionKind.new_entity,
        chosen_entity_id=None,
        review_id=review_id,
        confidence=0.4,
    )

    assert outcome.chosen_entity_id is None
    assert outcome.review_id == review_id


def test_entity_resolution_outcome_in_all() -> None:
    from app.schemas import extraction

    assert "EntityResolutionOutcome" in extraction.__all__


def test_extraction_all_is_alphabetical() -> None:
    from app.schemas import extraction

    assert list(extraction.__all__) == sorted(extraction.__all__)
