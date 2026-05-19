import uuid

from app.db.models_graph import EntityType, RelationType
from app.schemas.extraction import CandidateEntity, CandidateRelation


def _candidate_entity(
    quote: str,
    *,
    text_span: str | None = None,
) -> CandidateEntity:
    return CandidateEntity(
        text_span=text_span if text_span is not None else quote,
        suggested_type=EntityType.company,
        context_excerpt="...",
        exact_quote=quote,
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


def _candidate_relation(
    quote: str,
    *,
    subj_span: str | None = None,
    obj_span: str | None = None,
) -> CandidateRelation:
    return CandidateRelation(
        subj_span=subj_span if subj_span is not None else quote,
        predicate=RelationType.affects,
        obj_span=obj_span if obj_span is not None else quote,
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
    assert result.kept_entities[0].exact_quote == "Apple Inc."
    assert result.rejection_reasons == []


def test_verifier_rejects_one_character_substitution() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue in Q4."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple lnc.")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    assert "Apple lnc." in result.rejection_reasons[0]


def test_verifier_rejects_capitalization_change() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("apple inc.")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


def test_verifier_rejects_punctuation_change() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple Inc reported record revenue")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


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
    assert "Microsoft acquired LinkedIn" in result.rejection_reasons[0]


def test_verifier_rejects_empty_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    result = verify_candidates(
        chunk_text="anything",
        candidate_entities=[_candidate_entity("", text_span="Empty")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    assert "empty" in result.rejection_reasons[0].lower()
    assert "Empty" in result.rejection_reasons[0]


def test_verifier_rejects_whitespace_only_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    result = verify_candidates(
        chunk_text="Apple reported record revenue.",
        candidate_entities=[_candidate_entity("   \t\n  ", text_span="Whitespace")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    assert "empty" in result.rejection_reasons[0].lower()


def test_verifier_normalizes_whitespace_runs_in_chunk() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple    reported  record  revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple reported record revenue.")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_normalizes_newlines_to_single_space() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple\nreported\nrecord\nrevenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple reported record revenue.")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_normalizes_tabs_to_single_space() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple\treported\trecord\trevenue."
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

    chunk_text = "He said 'no comment' at the briefing."
    smart_quoted = "He said ‘no comment’ at the briefing."  # noqa: RUF001
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity(smart_quoted)],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


def test_verifier_rejects_em_dash_substitution() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Revenue - up 12% YoY - beat expectations."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Revenue — up 12% YoY — beat expectations.")],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1


def test_verifier_keeps_quote_that_is_substring_in_middle() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "On Monday Apple Inc. filed an 8-K with the SEC reporting earnings."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("filed an 8-K with the SEC")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_verifies_relations_independently() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[_candidate_relation("Apple supplies chips to its data centers.")],
    )

    assert len(result.kept_relations) == 1
    assert result.rejection_reasons == []


def test_verifier_rejects_relation_with_fabricated_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[_candidate_relation("Apple bought a chip foundry in Taiwan.")],
    )

    assert result.kept_relations == []
    assert len(result.rejection_reasons) == 1


def test_verifier_rejects_relation_with_empty_quote_using_subj_span_label() -> None:
    from app.services.extraction._verifier import verify_candidates

    result = verify_candidates(
        chunk_text="Apple supplies chips to its data centers.",
        candidate_entities=[],
        candidate_relations=[_candidate_relation("", subj_span="EmptySubj")],
    )

    assert result.kept_relations == []
    assert len(result.rejection_reasons) == 1
    assert "EmptySubj" in result.rejection_reasons[0]


def test_verifier_separates_kept_and_rejected_in_mixed_input() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple released a new phone."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity("Apple released a new phone."),
            _candidate_entity("Microsoft launched a tablet."),
        ],
        candidate_relations=[
            _candidate_relation("Apple released a new phone."),
            _candidate_relation("IBM revived OS/2 today."),
        ],
    )

    assert len(result.kept_entities) == 1
    assert len(result.kept_relations) == 1
    assert len(result.rejection_reasons) == 2


def test_verifier_rejection_reason_quotes_the_offending_text() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple released a new phone."
    bogus_quote = "Microsoft launched a tablet."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity(bogus_quote)],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    reason = result.rejection_reasons[0]
    assert reason.startswith("quote not in source:")
    assert bogus_quote in reason


def test_verifier_normalizes_internal_runs_inside_quote_too() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[_candidate_entity("Apple   reported    record  revenue.")],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_returns_empty_result_for_empty_inputs() -> None:
    from app.services.extraction._verifier import verify_candidates

    result = verify_candidates(
        chunk_text="anything",
        candidate_entities=[],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert result.kept_relations == []
    assert result.rejection_reasons == []


def test_verifier_preserves_order_of_kept_entities() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "alpha beta gamma"
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity("alpha"),
            _candidate_entity("beta"),
            _candidate_entity("gamma"),
        ],
        candidate_relations=[],
    )

    assert [c.text_span for c in result.kept_entities] == ["alpha", "beta", "gamma"]


def test_verifier_rejects_entity_when_text_span_not_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue in Q4."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity(
                "Apple Inc. reported record revenue",
                text_span="Microsoft",
            )
        ],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    reason = result.rejection_reasons[0]
    assert "text_span" in reason
    assert "Microsoft" in reason


def test_verifier_rejects_relation_when_subj_span_not_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[
            _candidate_relation(
                "Apple supplies chips to its data centers.",
                subj_span="Microsoft",
                obj_span="data centers",
            )
        ],
    )

    assert result.kept_relations == []
    assert len(result.rejection_reasons) == 1
    reason = result.rejection_reasons[0]
    assert "subj_span" in reason
    assert "Microsoft" in reason


def test_verifier_rejects_relation_when_obj_span_not_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[
            _candidate_relation(
                "Apple supplies chips to its data centers.",
                subj_span="Apple",
                obj_span="Foxconn",
            )
        ],
    )

    assert result.kept_relations == []
    assert len(result.rejection_reasons) == 1
    reason = result.rejection_reasons[0]
    assert "obj_span" in reason
    assert "Foxconn" in reason


def test_verifier_keeps_entity_when_text_span_is_partial_match_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue in Q4."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity(
                "Apple Inc. reported record revenue",
                text_span="Apple Inc.",
            )
        ],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_keeps_relation_when_both_spans_appear_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple supplies chips to its data centers."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[],
        candidate_relations=[
            _candidate_relation(
                "Apple supplies chips to its data centers.",
                subj_span="Apple",
                obj_span="data centers",
            )
        ],
    )

    assert len(result.kept_relations) == 1
    assert result.rejection_reasons == []


def test_verifier_normalizes_whitespace_when_checking_text_span_in_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity(
                "Apple Inc. reported record revenue.",
                text_span="Apple   Inc.",
            )
        ],
        candidate_relations=[],
    )

    assert len(result.kept_entities) == 1


def test_verifier_rejects_entity_with_empty_text_span_distinct_from_empty_quote() -> None:
    from app.services.extraction._verifier import verify_candidates

    chunk_text = "Apple Inc. reported record revenue."
    result = verify_candidates(
        chunk_text=chunk_text,
        candidate_entities=[
            _candidate_entity(
                "Apple Inc. reported record revenue.",
                text_span="   ",
            )
        ],
        candidate_relations=[],
    )

    assert result.kept_entities == []
    assert len(result.rejection_reasons) == 1
    assert "text_span" in result.rejection_reasons[0]
