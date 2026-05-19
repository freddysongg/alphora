import uuid

import pydantic
import pytest


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
    assert candidate.suggested_type == EntityType.company


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
    assert rel.is_explicit is True


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
    assert result.rejection_reasons == []


def test_extraction_module_all_includes_candidates() -> None:
    from app.schemas import extraction

    for name in ("CandidateEntity", "CandidateRelation", "ExtractionResult"):
        assert name in extraction.__all__


def test_extraction_module_all_is_sorted() -> None:
    from app.schemas import extraction

    assert list(extraction.__all__) == sorted(extraction.__all__)


def test_candidate_entity_is_immutable() -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import CandidateEntity

    candidate = CandidateEntity(
        text_span="Apple",
        suggested_type=EntityType.company,
        context_excerpt="...",
        exact_quote="Apple",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.5,
    )
    with pytest.raises(pydantic.ValidationError):
        candidate.text_span = "Microsoft"  # type: ignore[misc]


def test_candidate_relation_is_immutable() -> None:
    from app.db.models_graph import RelationType
    from app.schemas.extraction import CandidateRelation

    rel = CandidateRelation(
        subj_span="Apple",
        predicate=RelationType.regulated_by,
        obj_span="SEC",
        exact_quote="Apple is regulated by the SEC",
        chunk_id=uuid.uuid4(),
        is_explicit=True,
        extraction_confidence=0.9,
    )
    with pytest.raises(pydantic.ValidationError):
        rel.predicate = RelationType.affects  # type: ignore[misc]


def test_extraction_result_is_immutable() -> None:
    from app.schemas.extraction import ExtractionResult

    result = ExtractionResult(
        chunk_id=uuid.uuid4(),
        candidate_entities=[],
        candidate_relations=[],
        model_id="gpt-4o-mini",
        prompt_version="extraction-v1",
        verified=False,
        rejection_reasons=["quote not in source: 'x'"],
    )
    with pytest.raises(pydantic.ValidationError):
        result.verified = True  # type: ignore[misc]
